"""Warm daemon — keep pyobjc loaded so agent steps aren't cold-starting Python.

Security:
  - Socket mode 0600 (owner only)
  - Token file ~/.desktop-harness/daemon.token (0600); every request must include it
  - Single-instance via flock on the PID file (not a ping — exec holds the
    accept thread, so a busy daemon cannot answer)

Protocol (newline-delimited JSON over Unix socket):
  → {"op":"exec","code":"…","token":"…"}
  ← {"ok":true,"stdout":"...","stderr":""}
"""
from __future__ import annotations

import fcntl
import io
import json
import os
import secrets
import socket
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SOCKET_PATH = Path(os.environ.get(
    "DH_SOCKET",
    Path.home() / "Library" / "Caches" / "desktop-harness" / "daemon.sock",
))
PID_PATH = SOCKET_PATH.with_suffix(".pid")
TOKEN_PATH = Path(os.environ.get(
    "DH_TOKEN_PATH",
    Path.home() / ".desktop-harness" / "daemon.token",
))

# Presence (halo + Working · Stop chip) is shown by scripts run through
# this daemon and is only ever hidden by a script explicitly calling
# hide_agent_presence(), a Stop click on the chip, or the idle timeout.
# The daemon outlives any single script — if the calling agent's turn
# just ends, nothing else revisits that state. ACCEPT_POLL_SECONDS makes
# the accept() loop wake up so we can (a) idle-hide and (b) pump AppKit
# so a Stop click still lands between scripts. Both run on the daemon's
# single (main) thread — required, see presence.py's threading note.
ACCEPT_POLL_SECONDS = 0.35
PRESENCE_IDLE_HIDE_SECONDS = float(os.environ.get("DH_PRESENCE_IDLE_HIDE", "20"))
MAX_REQUEST_BYTES = 4 << 20  # 4 MiB; exec payloads are scripts, not dumps

# Held for the process lifetime so the exclusive lock stays with us.
_lock_fd: int | None = None


def socket_path() -> Path:
    return SOCKET_PATH


def _recv_timeout() -> float:
    try:
        return max(0.2, min(float(os.environ.get("DH_RECV_TIMEOUT", "5")), 60.0))
    except ValueError:
        return 5.0


def _write_0600(path: Path, text: str) -> None:
    """Create/replace a file that is 0600 from the first byte (no umask window)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, text.encode())
    finally:
        os.close(fd)


def _read_token() -> str | None:
    try:
        if TOKEN_PATH.exists():
            return TOKEN_PATH.read_text().strip() or None
    except Exception:
        pass
    return None


def _write_token() -> str:
    tok = secrets.token_hex(24)
    _write_0600(TOKEN_PATH, tok)
    return tok


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_from_file() -> int | None:
    try:
        if not PID_PATH.exists():
            return None
        old = int(PID_PATH.read_text().strip())
        if old > 0:
            return old
    except (ValueError, OSError):
        return None
    return None


def _live_daemon_pid() -> int | None:
    """PID of a still-alive process named in the pid file, if any.

    Paired with the socket path in ``is_running`` so a busy daemon (exec
    holds the accept thread) still counts as running, without a ping that
    would time out. Recycled pids fail closed once the socket is up.
    """
    old = _pid_from_file()
    if old is None or old == os.getpid():
        return None
    if _pid_alive(old):
        return old
    return None


def is_running() -> bool:
    # Inside the daemon process a ping would deadlock (single-threaded
    # accept loop is busy running the current script).
    if os.environ.get("DH_IN_DAEMON") == "1":
        return True
    live = _live_daemon_pid() is not None
    sock = SOCKET_PATH.exists()
    if live and sock:
        # Pid is up and the socket is bound. Do not ping — exec holds
        # the accept thread, so a 0.4s ping looks like a dead daemon.
        return True
    if not sock:
        return False
    try:
        resp = client_request({"op": "ping"}, timeout=0.4)
        return bool(resp.get("ok") and resp.get("pong"))
    except Exception:
        return False


def client_request(payload: dict, timeout: float = 60.0) -> dict:
    tok = _read_token()
    if tok and "token" not in payload:
        payload = {**payload, "token": tok}
    data = (json.dumps(payload) + "\n").encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(SOCKET_PATH))
        s.sendall(data)
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            buf += chunk
    if not buf:
        raise RuntimeError("daemon closed connection")
    return json.loads(buf.decode())


def exec_via_daemon(code: str, timeout: float = 60.0) -> dict:
    return client_request({"op": "exec", "code": code}, timeout=timeout)


def _acquire_instance_lock() -> None:
    """Exclusive flock on the pid file. Fail closed if another daemon holds it.

    A ping cannot be the single-instance check: exec runs inline on the
    accept loop, so a busy daemon looks dead to a 0.4s ping and a second
    start would unlink the live socket and mint a new token.
    """
    global _lock_fd
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(PID_PATH), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        old = "?"
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            old = os.read(fd, 32).decode().strip() or "?"
        except Exception:
            pass
        os.close(fd)
        raise SystemExit(
            f"daemon already running (pid {old}). "
            f"Use: desktop-harness daemon stop"
        )
    except Exception:
        os.close(fd)
        raise
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, f"{os.getpid()}\n".encode())
    _lock_fd = fd


def _release_instance_lock() -> None:
    global _lock_fd
    fd = _lock_fd
    _lock_fd = None
    if fd is None:
        return
    try:
        PID_PATH.unlink()
    except OSError:
        pass
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def _recv_request(conn: socket.socket) -> bytes | None:
    """Read one newline-terminated request, or None to drop the connection.

    The listening socket's accept() timeout does not inherit onto the
    accepted conn. Without a timeout here, a client that connects and
    never sends a newline parks recv() forever — before auth — and the
    single accept thread cannot deliver a Stop click or idle-hide.
    """
    conn.settimeout(_recv_timeout())
    buf = b""
    try:
        while b"\n" not in buf:
            if len(buf) >= MAX_REQUEST_BYTES:
                return None
            chunk = conn.recv(min(1 << 16, MAX_REQUEST_BYTES - len(buf)))
            if not chunk:
                break
            buf += chunk
    except (TimeoutError, socket.timeout):
        return None
    if not buf or b"\n" not in buf:
        return None
    # Exec (and the reply) can outlive the recv timeout.
    conn.settimeout(None)
    return buf


def serve() -> None:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    _acquire_instance_lock()
    try:
        _serve_locked()
    finally:
        try:
            SOCKET_PATH.unlink()
        except OSError:
            pass
        _release_instance_lock()


def _serve_locked() -> None:
    if SOCKET_PATH.exists():
        try:
            SOCKET_PATH.unlink()
        except OSError:
            pass

    token = _write_token()
    os.environ["DH_IN_DAEMON"] = "1"

    from .helpers import namespace

    ns = namespace()
    ns["helpers"] = __import__("desktop_harness.helpers", fromlist=["*"])

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        old_umask = os.umask(0o077)
        try:
            srv.bind(str(SOCKET_PATH))
        finally:
            os.umask(old_umask)
        try:
            os.chmod(SOCKET_PATH, 0o600)
        except OSError:
            pass
        srv.listen(8)
        # Times out accept() periodically so the idle-presence check below runs
        # even when no request comes in; the *accepted* connection socket does
        # not inherit this (Python only forces blocking on it when no global
        # default timeout is set). _recv_request sets its own timeout; in-flight
        # execs then go back to blocking so long scripts are unaffected.
        srv.settimeout(ACCEPT_POLL_SECONDS)
        print(f"desktop-harness daemon listening on {SOCKET_PATH}", flush=True)
        print(f"token: {TOKEN_PATH} (0600)", flush=True)

        last_activity = time.monotonic()
        while True:
            try:
                conn, _ = srv.accept()
            except (TimeoutError, socket.timeout):
                # Deliver a Stop click that landed between scripts, then
                # self-clear a stale presence overlay.
                try:
                    from . import presence
                    presence.poll(deep=True)
                except Exception:
                    pass
                idle = time.monotonic() - last_activity
                if idle >= PRESENCE_IDLE_HIDE_SECONDS:
                    try:
                        from . import presence
                        if presence.active():
                            presence.hide()
                        # Session over — a later turn can drive the Mac again.
                        presence.clear_stop()
                    except Exception:
                        pass
                    try:
                        from . import stage as _stage
                        if _stage.monitor_active():
                            _stage.hide_monitor()
                    except Exception:
                        pass
                continue
            with conn:
                def _reply(payload: bytes | dict) -> None:
                    # Client may have closed (timeout, killed agent) — never
                    # let a BrokenPipe take down the whole daemon; that left
                    # agents hung on a dead socket looking like "shell stuck".
                    try:
                        if isinstance(payload, dict):
                            payload = (json.dumps(payload) + "\n").encode()
                        conn.sendall(payload)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass

                buf = _recv_request(conn)
                if not buf:
                    continue
                line = buf.split(b"\n", 1)[0]
                try:
                    req = json.loads(line.decode())
                except json.JSONDecodeError as e:
                    _reply({"ok": False, "error": str(e)})
                    continue
                # Auth
                if req.get("token") != token:
                    _reply(b'{"ok":false,"error":"unauthorized (bad or missing token)"}\n')
                    continue
                op = req.get("op")
                if op == "ping":
                    _reply(b'{"ok":true,"pong":true}\n')
                    continue
                if op == "quit":
                    _reply(b'{"ok":true}\n')
                    break
                if op == "exec":
                    code = req.get("code") or ""
                    out_b, err_b = io.StringIO(), io.StringIO()
                    ok = True
                    err_msg = ""
                    try:
                        with redirect_stdout(out_b), redirect_stderr(err_b):
                            exec(
                                compile(code, "<desktop-harness-daemon>", "exec"),
                                ns,
                                ns,
                            )
                    except Exception as e:
                        ok = False
                        from .presence import ControlStopped
                        from .input import PointerTaken
                        if isinstance(e, (ControlStopped, PointerTaken)):
                            err_msg = f"stopped: {e}\n"
                        else:
                            err_msg = traceback.format_exc()
                    last_activity = time.monotonic()
                    _reply({
                        "ok": ok,
                        "stdout": out_b.getvalue(),
                        "stderr": err_b.getvalue() + err_msg,
                    })
                    continue
                _reply({"ok": False, "error": f"unknown op {op}"})
    finally:
        try:
            srv.close()
        except OSError:
            pass
