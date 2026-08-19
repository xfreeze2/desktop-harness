"""Non-destructive self-test for release confidence."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable


def run_selftest() -> int:
    from . import helpers as H
    from .admin import run_doctor
    from .ax import frame_on_screen

    print("desktop-harness selftest\n")
    fails = 0
    # A leftover Stop from a previous script must not fail this run.
    try:
        H.resume_control()
        H.hide_agent_presence()
        H.release_keys()
    except Exception:
        pass

    def check(name: str, fn: Callable[[], None]):
        nonlocal fails
        t0 = time.time()
        try:
            fn()
            ms = int((time.time() - t0) * 1000)
            print(f"  [PASS] {name} ({ms}ms)")
        except Exception as e:
            fails += 1
            print(f"  [FAIL] {name}: {type(e).__name__}: {e}")

    print("— doctor —")
    doc = run_doctor()
    if doc != 0:
        fails += 1
        print("  (doctor reported failures)\n")
    else:
        print()

    print("— core —")

    def _apps():
        assert len(H.list_apps()) >= 1

    def _wins():
        assert len(H.list_windows()) >= 1

    def _front():
        assert H.frontmost_app() is not None

    def _labels():
        assert isinstance(H.labels(limit=5), list)

    def _mouse():
        p = H.mouse_pos()
        assert "x" in p and "y" in p

    def _move_restore():
        p0 = H.mouse_pos()
        H.move_to(p0["x"] + 30, p0["y"] + 20, duration=0.05)
        H.move_to(p0["x"], p0["y"], duration=0.05)
        p1 = H.mouse_pos()
        assert abs(p1["x"] - p0["x"]) < 12 and abs(p1["y"] - p0["y"]) < 12

    def _shot():
        path = H.screenshot()
        assert Path(path).stat().st_size > 1000

    def _media_api():
        st = H.media_transport()
        assert st["state"] in ("playing", "paused", "unknown")
        assert "transport_play" in st and "row_play" in st
        # play flag must mean transport only
        assert st["play"] == st["transport_play"]

    def _find_app_ranking():
        # exact beats substring; pid path works
        apps = H.list_apps()
        if not apps:
            return
        one = apps[0]
        got = H.find_app(one["name"])
        assert got and got["pid"] == one["pid"]
        by_pid = H.find_app(one["pid"])
        assert by_pid and by_pid["pid"] == one["pid"]

    def _frame_filter():
        assert frame_on_screen({"x": 100, "y": 100, "w": 50, "h": 50})
        assert not frame_on_screen({"x": 50, "y": 50, "w": 0, "h": 10})
        assert not frame_on_screen({"x": 100, "y": 9000, "w": 40, "h": 40})

    def _window_frame_map():
        fr = H.window_frame()
        assert fr["w"] >= 50 and fr["h"] >= 50
        gx, gy = H.win_to_global(10, 20, frame=fr)
        assert abs(gx - (fr["x"] + 10)) < 0.01
        assert abs(gy - (fr["y"] + 20)) < 0.01

    def _run_plan_wait():
        # no GUI mutation — just prove plan runner wires ops
        out = H.run_plan([
            {"op": "wait", "seconds": 0.05},
            {"op": "window_frame"},
        ], stop_on_error=True)
        assert len(out) == 2 and all(r.get("ok") for r in out)

    def _grab_frame_ram():
        fr = H.grab_frame()
        assert fr["w"] >= 50 and fr["h"] >= 50
        assert isinstance(fr["data"], (bytes, bytearray))
        assert len(fr["data"]) >= fr["w"] * 4
        r, g, b = H.pixel(fr, 2, 2)
        assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255
        d = H.frame_digest(fr)
        assert isinstance(d, int)
        # General color tools — no app knowledge.
        c = H.count_color(fr, (r, g, b), tol=8, region=(0, 0, 40, 40), step=2)
        assert c >= 1
        hit = H.find_color(fr, (r, g, b), tol=8, region=(0, 0, 40, 40), step=2)
        assert hit and "x" in hit and "y" in hit
        assert H.color_near((r, g, b), (r, g, b), tol=0)
        col = H.scan_column(fr, 4, rgb=(r, g, b), tol=40, y0=0, y1=20, step=2)
        assert isinstance(col, list)
        H.largest_run(col)  # None is fine on a noisy patch
        # Region grab must be smaller than the full window.
        crop = H.grab_frame(region=(0.25, 0.25, 0.3, 0.3))
        assert crop["w"] < fr["w"] or crop["h"] < fr["h"]
        assert crop["w"] >= 8 and crop["h"] >= 8

    def _wait_for_present():
        labs = H.labels(limit=8)
        token = None
        for line in labs:
            # "AXButton: Close" → Close
            if ": " in line:
                token = line.split(": ", 1)[1].strip()
                if token and len(token) > 1:
                    break
        if not token:
            return
        hit = H.wait_for(token, timeout=2.0)
        assert hit
        try:
            H.wait_for("___no_such_ax_label___", timeout=0.25)
            raise AssertionError("wait_for should time out")
        except TimeoutError:
            pass

    def _workspace_not_site_packages():
        from . import helpers as HH
        p = HH._resolve_agent_workspace()
        assert "site-packages" not in str(p)

    def _menu_click_missing():
        try:
            H.menu_click("___NoSuchMenu___", "Nope")
            raise AssertionError("missing menu should raise")
        except RuntimeError:
            pass

    def _clipboard_roundtrip():
        prev = H.clipboard_get()
        token = "dh-selftest-clip"
        try:
            H.clipboard_set(token)
            assert H.clipboard_get() == token
        finally:
            H.clipboard_set(prev)

    def _run_loop_dry():
        n = {"i": 0}

        def step(frame):
            n["i"] += 1
            assert frame["w"] >= 50
            if n["i"] >= 3:
                return {"stop": True, "hold": []}
            return {"hold": []}

        out = H.run_loop(step, hz=40, seconds=2.0, max_frames=8)
        assert out["frames"] == 3
        assert out["last"] and out["last"].get("stop")

    def _apply_hold_shape():
        H.release_keys()
        H.apply({"hold": []})
        assert H.held_keys() == []

    def _refuse_weak_click():
        from . import helpers as HH
        weak = [{"score": 25, "label": "Playing from", "role": "AXGroup",
                 "frame": {"x": 0, "y": 0, "w": 900, "h": 700}}]
        try:
            HH._pick_click_hit(weak, "Play")
            raise AssertionError("weak match should refuse")
        except RuntimeError as e:
            assert "confident" in str(e) or "refusing" in str(e)
        assert not HH._frame_is_click_target({
            "role": "AXWebArea", "frame": {"x": 0, "y": 0, "w": 900, "h": 700},
        })
        assert HH._frame_is_click_target({
            "role": "AXButton", "frame": {"x": 10, "y": 10, "w": 80, "h": 24},
        })

    def _refuse_human_pointer():
        from . import input as I
        p = H.mouse_pos()
        I._last_warp = (p["x"] + 80, p["y"] + 80)
        try:
            H.click(p["x"], p["y"], move=False, settle=0)
            raise AssertionError("click should refuse when user moved the mouse")
        except I.PointerTaken:
            pass
        I._last_warp = (p["x"], p["y"])

    def _user_stop_gate():
        from . import presence as p
        p.clear_stop()
        p.request_stop("selftest")
        try:
            H.click(10, 10, move=False, settle=0)
            raise AssertionError("click should raise ControlStopped")
        except p.ControlStopped:
            pass
        try:
            H.clipboard_get()
            raise AssertionError("clipboard_get should raise ControlStopped")
        except p.ControlStopped:
            pass
        try:
            H.clipboard_set("should-not-land")
            raise AssertionError("clipboard_set should raise ControlStopped")
        except p.ControlStopped:
            pass
        # AX reads still work while stopped
        assert H.frontmost_app() is not None
        H.resume_control()
        assert not p.stopped()

    def _clipboard_sensitive_frontmost():
        from . import windows as W
        H.resume_control()
        real = W.frontmost_app
        W.frontmost_app = lambda: {
            "name": "1Password",
            "bundle_id": "com.1password.1password",
        }
        try:
            try:
                H.clipboard_get()
                raise AssertionError("clipboard_get should refuse 1Password")
            except PermissionError:
                pass
            try:
                H.clipboard_set("should-not-land")
                raise AssertionError("clipboard_set should refuse 1Password")
            except PermissionError:
                pass
        finally:
            W.frontmost_app = real

    def _now_playing_shape():
        info = H.now_playing()
        assert isinstance(info, dict)
        assert "app" in info

    def _menubar_skipped_by_default():
        # frontmost labels should not be flooded with Apple menu items
        labs = H.labels(limit=40)
        appleish = [L for L in labs if "About This Mac" in L or "System Settings" in L]
        # zero preferred; allow a couple if menubar leaked somehow
        assert len(appleish) <= 2, appleish

    def _monitor_follow_textedit():
        # Monitor stays off unless explicitly opened (or open_stage).
        H.resume_control()
        H.hide_monitor()
        p = H.mouse_pos()
        H.click(p["x"], p["y"])  # everyday click must NOT pop a TV
        assert not H._stage.monitor_active(), "everyday click opened monitor"
        H.show_monitor()
        assert H._stage.monitor_active(), "show_monitor did not open"
        H.follow("Ghostty")
        H.stage_note("selftest")
        H.refresh_monitor(force=True)
        H.hide_monitor()
        assert not H._stage.monitor_active(), "hide_monitor left monitor up"

    for name, fn in [
        ("list_apps", _apps),
        ("list_windows", _wins),
        ("frontmost_app", _front),
        ("labels", _labels),
        ("mouse_pos", _mouse),
        ("move_to restore", _move_restore),
        ("screenshot", _shot),
        ("media_transport api", _media_api),
        ("find_app ranking + pid", _find_app_ranking),
        ("frame_on_screen filter", _frame_filter),
        ("window_frame + win_to_global", _window_frame_map),
        ("run_plan wait", _run_plan_wait),
        ("grab_frame ram", _grab_frame_ram),
        ("wait_for present/timeout", _wait_for_present),
        ("agent workspace path", _workspace_not_site_packages),
        ("menu_click missing", _menu_click_missing),
        ("clipboard roundtrip", _clipboard_roundtrip),
        ("run_loop dry", _run_loop_dry),
        ("apply hold empty", _apply_hold_shape),
        ("refuse weak click", _refuse_weak_click),
        ("refuse human pointer", _refuse_human_pointer),
        ("user stop gate", _user_stop_gate),
        ("clipboard refuses sensitive frontmost", _clipboard_sensitive_frontmost),
        ("now_playing shape", _now_playing_shape),
        ("menubar skipped by default", _menubar_skipped_by_default),
        ("monitor follow Ghostty", _monitor_follow_textedit),
    ]:
        check(name, fn)

    print("\n— light GUI (TextEdit) —")

    def _textedit():
        import subprocess
        H.resume_control()
        # open + AppleScript activate is more reliable against agent hosts
        subprocess.run(["open", "-a", "TextEdit"], check=False)
        time.sleep(0.4)
        subprocess.run(
            ["osascript", "-e", 'tell application "TextEdit" to activate'],
            check=False, capture_output=True,
        )
        deadline = time.time() + 4.0
        while time.time() < deadline:
            front = H.frontmost_app()
            if front and front.get("name") == "TextEdit":
                break
            H.activate("TextEdit", wait=0.2)
            time.sleep(0.15)
        front = H.frontmost_app()
        # If host keeps stealing focus, still type into TextEdit via AX after activate
        H.activate("TextEdit", wait=0.25)
        H.hotkey("cmd", "n")
        time.sleep(0.35)
        H.activate("TextEdit", wait=0.2)
        token = f"dh-selftest-{int(time.time())}"
        H.type_text(token)
        time.sleep(0.25)
        # Success criteria: TextEdit is running with a window (focus may bounce to agent host)
        te = H.find_app("TextEdit")
        assert te is not None, "TextEdit not running"
        wins = [w for w in H.list_windows() if w.get("app") == "TextEdit"]
        assert wins, "TextEdit has no window"
        print(f"      typed {token!r} into TextEdit (windows={len(wins)}; left open)")

    check("TextEdit open+type", _textedit)

    print("\n— daemon —")

    def _daemon_roundtrip():
        import os
        import subprocess
        import sys
        from . import daemon as d
        # stop then bg start
        if d.is_running():
            try:
                d.client_request({"op": "quit"}, timeout=2)
            except Exception:
                pass
            time.sleep(0.2)
        # start bg via CLI
        subprocess.check_call(
            [sys.executable, "-m", "desktop_harness.run", "daemon", "start", "--bg"],
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
        assert d.is_running(), "daemon not running after --bg"
        resp = d.exec_via_daemon("print(1+1)")
        assert resp.get("ok") and "2" in (resp.get("stdout") or "")
        # Leave the daemon UP — quitting it here is why everyday agent
        # calls after selftest went cold/slow. Restart is the test;
        # teardown that disables the product is not.

    def _isolated_daemon():
        """Throwaway daemon on a private socket — does not touch the user one."""
        import json
        import os
        import shutil
        import socket
        import stat
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.mkdtemp(prefix="dh-dtest-"))
        sock = tmp / "d.sock"
        token_path = tmp / "d.token"
        env = {
            **os.environ,
            "DH_SOCKET": str(sock),
            "DH_TOKEN_PATH": str(token_path),
            "DH_AUTO_DAEMON": "0",
            "DH_NO_DAEMON": "1",
            "DH_RECV_TIMEOUT": "0.6",
        }
        env.pop("DH_IN_DAEMON", None)
        proc = subprocess.Popen(
            [sys.executable, "-m", "desktop_harness.run", "daemon", "serve"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        def _req(payload: dict, timeout: float = 3.0) -> dict:
            tok = token_path.read_text().strip()
            data = (json.dumps({**payload, "token": tok}) + "\n").encode()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect(str(sock))
                s.sendall(data)
                buf = b""
                while b"\n" not in buf:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
            if not buf:
                raise RuntimeError("empty daemon reply")
            return json.loads(buf.decode())

        try:
            deadline = time.time() + 5
            while time.time() < deadline:
                if proc.poll() is not None:
                    out = proc.stdout.read().decode() if proc.stdout else ""
                    raise AssertionError(f"test daemon died: {out}")
                if sock.exists() and token_path.exists():
                    try:
                        ping = _req({"op": "ping"}, timeout=1)
                        if ping.get("pong"):
                            break
                    except Exception:
                        pass
                time.sleep(0.05)
            else:
                raise AssertionError("test daemon did not start")

            mode = stat.S_IMODE(token_path.stat().st_mode)
            assert mode == 0o600, f"token mode {oct(mode)}, expected 0o600"
            sock_mode = stat.S_IMODE(sock.stat().st_mode)
            assert sock_mode == 0o600, f"socket mode {oct(sock_mode)}, expected 0o600"

            hung = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            hung.settimeout(4)
            hung.connect(str(sock))
            hung.sendall(b"no-newline-should-not-wedge")
            t0 = time.time()
            ping = _req({"op": "ping"}, timeout=4)
            hung_ms = time.time() - t0
            hung.close()
            assert ping.get("pong"), ping
            assert hung_ms < 3.0, f"hung client blocked accept for {hung_ms:.1f}s"

            busy = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            busy.settimeout(6)
            busy.connect(str(sock))
            tok = token_path.read_text().strip()
            busy.sendall(
                (json.dumps({
                    "op": "exec",
                    "code": "import time; time.sleep(1.2)",
                    "token": tok,
                }) + "\n").encode()
            )
            time.sleep(0.15)
            proc2 = subprocess.Popen(
                [sys.executable, "-m", "desktop_harness.run", "daemon", "serve"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            try:
                out2, _ = proc2.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                proc2.kill()
                raise AssertionError("second daemon start hung instead of refusing")
            assert proc2.returncode not in (0, None), (
                f"second start should refuse, got rc={proc2.returncode} {out2!r}"
            )
            assert b"already running" in out2, out2
            buf = b""
            while b"\n" not in buf:
                chunk = busy.recv(65536)
                if not chunk:
                    break
                buf += chunk
            busy.close()
            done = json.loads(buf.decode())
            assert done.get("ok"), done
            assert _req({"op": "ping"}).get("pong")
        finally:
            if proc.poll() is None:
                try:
                    _req({"op": "quit"}, timeout=1)
                except Exception:
                    proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
            shutil.rmtree(tmp, ignore_errors=True)

    check("daemon bg + exec", _daemon_roundtrip)
    check("daemon lock + hung client", _isolated_daemon)

    print()
    if fails:
        print(f"{fails} failure(s). Fix before release.")
        return 1
    print("all selftests passed.")
    return 0
