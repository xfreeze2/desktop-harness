"""Agent-facing helpers — pre-imported into every desktop-harness script.

Efficiency order:
  1. shell / APIs (outside this package)
  2. ax_snapshot / find / click_text / set_field  (AX-first)
  3. screenshot + coordinate click               (fallback)
"""
from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path
from typing import Any

from . import ax as _ax
from . import capture as _capture
from . import input as _input
from . import presence as _presence
from . import windows as _windows

ControlStopped = _presence.ControlStopped
PointerTaken = _input.PointerTaken

CORE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CORE_DIR.parent.parent


def _resolve_agent_workspace() -> Path:
    """Where optional ``agent_helpers.py`` is loaded from.

    Editable checkout: ``<repo>/agent-workspace``.
    A wheel in site-packages has no repo next to it — don't invent a
    path inside site-packages. Fall back to ``~/.desktop-harness/agent-workspace``.
    """
    env = os.environ.get("DH_AGENT_WORKSPACE")
    if env:
        return Path(env).expanduser()
    source = REPO_ROOT / "agent-workspace"
    if source.is_dir():
        return source
    return Path.home() / ".desktop-harness" / "agent-workspace"


AGENT_WORKSPACE = _resolve_agent_workspace()


# --- re-exports ---

list_apps = _windows.list_apps
list_windows = _windows.list_windows
frontmost_app = _windows.frontmost_app
find_app = _windows.find_app
window_frame = _windows.window_frame
win_to_global = _windows.win_to_global
chip_frame = _presence.chip_frame


def _gate() -> None:
    """Abort if the user clicked Stop on the Working chip."""
    _presence.assert_running()


def resume_control() -> None:
    """Allow control again after a Stop. Only after the user asked to continue."""
    _presence.clear_stop()


def activate(*args, **kwargs):
    _gate()
    out = _windows.activate(*args, **kwargs)
    name = args[0] if args else kwargs.get("name_or_bundle")
    # Follow only if the live view is already up — do not pop it just
    # because we focused Ghostty after a task.
    try:
        if name is not None and not isinstance(name, int):
            if _presence.active() and str(name).lower() not in (
                "ghostty", "terminal", "iterm2",
            ):
                _presence.ring_window(str(name))
        if _stage.monitor_active() and name is not None and not isinstance(name, int):
            _stage.follow(str(name))
            _stage.stage_note(f"open {name}")
            _stage.refresh_monitor(force=True)
    except Exception:
        pass
    return out


def open_app(name: str):
    return activate(name)

ax_snapshot = _ax.ax_snapshot
find = _ax.find
focused_element = _ax.focused_element

screenshot = _capture.screenshot
grab_frame = _capture.grab_frame
pixel = _capture.pixel
frame_digest = _capture.frame_digest
color_near = _capture.color_near
find_color = _capture.find_color
count_color = _capture.count_color
scan_column = _capture.scan_column
scan_row = _capture.scan_row
largest_run = _capture.largest_run

from . import stage as _stage

open_stage = _stage.open_stage
close_stage = _stage.close_stage
stage_frame = _stage.stage_frame
show_monitor = _stage.show_monitor
hide_monitor = _stage.hide_monitor
follow = _stage.follow
stage_note = _stage.stage_note
refresh_monitor = _stage.refresh_monitor

# Mouse — real system pointer (you can watch it move)
mouse_pos = _input.mouse_pos
move_to = _input.move_to
move_by = _input.move_by
wiggle = _input.wiggle
key_down = _input.key_down
key_up = _input.key_up
keys_hold = _input.keys_hold
release_keys = _input.release_keys
held_keys = _input.held_keys
tap = _input.tap
mouse_down = _input.mouse_down
mouse_up = _input.mouse_up

from . import reflex as _reflex

run_loop = _reflex.run_loop
apply = _reflex.apply


def _watch(note: str | None = None, app: str | int | None = None) -> None:
    """Refresh the live view only if it is already open (Stage).

    Everyday control of an on-screen app does not pop a second picture
    of that app — the user can already see it.
    """
    try:
        if app is not None and not isinstance(app, int):
            if _presence.active() and str(app).lower() not in (
                "ghostty", "terminal", "iterm2",
            ):
                _presence.ring_window(str(app))
        if not _stage.monitor_active():
            return
        if note:
            _stage.stage_note(note)
        if app is not None and not isinstance(app, int):
            _stage.follow(str(app))
        _stage.refresh_monitor(force=False)
    except Exception:
        pass


def click(*args, **kwargs):
    from . import safety as _safety
    _safety.check_frontmost_allowed()
    _safety.audit("click", {"args": args[:2]})
    out = _input.click(*args, **kwargs)
    _watch("click")
    return out


def right_click(*args, **kwargs):
    from . import safety as _safety
    _safety.check_frontmost_allowed()
    _safety.audit("right_click", {"args": args[:2]})
    return _input.right_click(*args, **kwargs)


def click_frame(*args, **kwargs):
    from . import safety as _safety
    _safety.check_frontmost_allowed()
    _safety.audit("click_frame", {"args": args[:1]})
    return _input.click_frame(*args, **kwargs)


def drag(*args, **kwargs):
    from . import safety as _safety
    _safety.check_frontmost_allowed()
    _safety.audit("drag", {"args": args[:4]})
    return _input.drag(*args, **kwargs)


def click_in_window(
    x: float,
    y: float,
    app: str | int | None = None,
    *,
    frame: dict[str, Any] | None = None,
    **kwargs,
):
    """Click at window-local (screenshot) coordinates — maps via window_frame."""
    gx, gy = win_to_global(x, y, app, frame=frame)
    return click(gx, gy, **kwargs)


def drag_in_window(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    app: str | int | None = None,
    *,
    frame: dict[str, Any] | None = None,
    **kwargs,
):
    """Drag in window-local coords (screenshot space → global)."""
    g1 = win_to_global(x1, y1, app, frame=frame)
    g2 = win_to_global(x2, y2, app, frame=frame)
    return drag(g1[0], g1[1], g2[0], g2[1], **kwargs)


def scroll(*args, **kwargs):
    from . import safety as _safety
    _safety.check_frontmost_allowed()
    _safety.audit("scroll", {"args": args[:2]})
    return _input.scroll(*args, **kwargs)


def key(*args, **kwargs):
    from . import safety as _safety
    _safety.check_frontmost_allowed()
    _safety.audit("key", {"key": args[0] if args else None})
    return _input.key(*args, **kwargs)


def hotkey(*args, **kwargs):
    from . import safety as _safety
    _safety.check_frontmost_allowed()
    _safety.audit("hotkey", {"keys": args})
    return _input.hotkey(*args, **kwargs)


def media_key(name: str = "playpause", **kwargs):
    """System media key (playpause/next/prev/volumeup/volumedown/mute)."""
    from . import safety as _safety
    # Volume/mute are not app-targeted; still audit. Transport keys need
    # the frontmost gate so we don't poke a password manager.
    if name.lower() not in ("volumeup", "volup", "volumedown", "voldown", "mute"):
        _safety.check_frontmost_allowed()
    _safety.audit("media_key", {"name": name})
    return _input.media_key(name, **kwargs)


def now_playing(app: str | int | None = None) -> dict[str, Any]:
    """Cheap now-playing snapshot: window title + AX transport state.

    Prefer an already-open player (YT Music, Music, Spotify). Does not click.
    """
    target = app
    if target is None:
        names = ("YT Music", "YouTube Music", "Music", "Spotify", "YouTube")
        running = {a.get("name"): a for a in list_apps()}
        for n in names:
            if n in running:
                target = n
                break
        if target is None:
            front = frontmost_app()
            target = (front or {}).get("name")
    info: dict[str, Any] = {"app": target}
    try:
        fr = window_frame(target)
        info["title"] = fr.get("title") or ""
        info["window"] = {k: fr[k] for k in ("x", "y", "w", "h") if k in fr}
    except Exception as e:
        info["title_error"] = str(e)
    try:
        st = media_transport(target)
        info["state"] = st.get("state")
        info["pause"] = st.get("pause")
        info["play"] = st.get("play")
        info["labels"] = (st.get("labels") or [])[:12]
    except Exception as e:
        info["transport_error"] = str(e)
    return info


def type_text(*args, **kwargs):
    from . import safety as _safety
    _safety.check_frontmost_allowed()
    _safety.audit("type_text", {"n": len(args[0]) if args else 0})
    out = _input.type_text(*args, **kwargs)
    _watch("type")
    return out


def enable_agent_cursor(enabled: bool = True):
    """Show / hide agent presence (ice halo + Working · Stop chip).

    Design: ONE real system cursor + soft glow halo (never a second arrow).
    Ice while moving; brief amber flash on click. DH_PRESENCE=0 to disable.
    Click the bottom chip to stop the agent immediately.
    """
    try:
        if not enabled:
            _presence.hide()
            _input.set_overlay(None)
            return False
        # Explicit new control session — user asked the agent to work again.
        _presence.clear_stop()
        p = mouse_pos()
        ok = _presence.show(p["x"], p["y"])
        if ok:
            # Overlay uses presence.move(x,y) on every warp — same coords as cursor
            _input.set_overlay(_presence)
        return ok
    except Exception as e:
        print(f"agent presence unavailable: {e}")
        return False


def hide_agent_presence():
    """Hide ring, banner, and live monitor when a control sequence is finished.

    Call this when you know you're done — it's still the fast, immediate
    path. If a script forgets (crash, early return, the chat turn just
    ending), the warm daemon also self-clears presence after a stretch of
    no harness activity (see daemon.py's idle loop / DH_PRESENCE_IDLE_HIDE)
    so a missed call doesn't leave the overlay on screen indefinitely."""
    try:
        _input.release_keys()
    except Exception:
        pass
    try:
        _presence.hide()
    except Exception:
        pass
    try:
        _stage.hide_monitor()
    except Exception:
        pass
    _input.set_overlay(None)


def keep_alive(seconds: float) -> None:
    """Presence-safe wait. Same as wait(); exported so scripts can call it by name."""
    wait(seconds)


def wait(seconds: float = 0.4):
    """Pause — presence-safe: keeps the agent-presence overlay from
    sinking behind other windows during the wait, instead of a raw sleep
    that leaves it unattended. Prefer this over time.sleep() in scripts.

    Honors a Stop click on the Working chip (raises ControlStopped).
    """
    _presence.keep_alive(seconds)


def wait_stable(seconds: float = 0.2):
    """Short settle after an action (presence-safe; keep small for speed)."""
    wait(seconds)


def wait_for(
    text: str,
    app: str | int | None = None,
    *,
    role: str | None = None,
    exact: bool = False,
    timeout: float = 3.0,
    interval: float = 0.12,
) -> dict[str, Any]:
    """Poll AX ``find`` until a match appears, or raise TimeoutError.

    Use this instead of a blind ``wait(0.5)`` after a click that should
    open a sheet, menu, or dialog. Same eyes as everyday control — no
    screenshot loop.
    """
    deadline = time.monotonic() + max(0.05, float(timeout))
    last: list[dict[str, Any]] = []
    q = text.strip().lower()
    while time.monotonic() < deadline:
        _gate()
        last = _ax.find(text, app=app, role=role, max_results=6, include_el=False)
        if exact:
            last = [
                h for h in last
                if (h.get("title") or "").strip().lower() == q
                or (h.get("label") or "").strip().lower() == q
            ]
        if last:
            return last[0]
        wait(interval)
    raise TimeoutError(
        f"wait_for {text!r} timed out after {timeout}s "
        f"(role={role!r}, exact={exact})"
    )


def menu_click(*path: str, app: str | int | None = None) -> dict[str, Any]:
    """Press a menu item by exact titles: ``menu_click("File", "Save")``.

    Walks the AX menu bar. Each segment must match a title/label exactly
    (case-insensitive). No substring guessing — that clicks the wrong item.
    """
    from . import safety as _safety
    _gate()
    _safety.check_frontmost_allowed()
    if app:
        _safety.check_app_allowed(str(app))
    parts = [str(p).strip() for p in path if str(p).strip()]
    if not parts:
        raise ValueError("menu_click needs at least one title, e.g. File, Save")
    _safety.audit("menu_click", {"path": parts, "app": app})

    root, _pid = _ax.app_element(app)
    bar = _ax._copy(root, "AXMenuBar")
    if bar is None:
        raise RuntimeError(f"no menu bar for app {app!r}")

    current = bar
    target = None
    for i, name in enumerate(parts):
        q = name.lower()
        kids = _ax._children(current)
        match = None
        for kid in kids:
            title = _ax._str_attr(kid, "AXTitle")
            desc = _ax._str_attr(kid, "AXDescription")
            if title.lower() == q or desc.lower() == q:
                match = kid
                break
        if match is None:
            available = [
                _ax._str_attr(k, "AXTitle") or _ax._str_attr(k, "AXDescription")
                for k in kids
            ]
            available = [a for a in available if a][:20]
            raise RuntimeError(
                f"no exact menu match for {name!r} in {parts!r}. "
                f"visible: {available}"
            )
        if i == len(parts) - 1:
            target = match
            break
        menus = [
            k for k in _ax._children(match)
            if _ax._str_attr(k, "AXRole") == "AXMenu"
        ]
        if not menus:
            _ax.press_element(match)
            wait_stable(0.08)
            menus = [
                k for k in _ax._children(match)
                if _ax._str_attr(k, "AXRole") == "AXMenu"
            ]
        current = menus[0] if menus else match

    if target is None or not _ax.press_element(target):
        raise RuntimeError(f"could not press menu {parts!r}")
    wait_stable()
    return {"ok": True, "path": parts, "app": app}


def clipboard_get() -> str:
    """Plain text from the Mac clipboard. Empty string if none.

    Gated like an unscoped screenshot: a password manager's whole flow is
    "copy the secret to the clipboard", so reading it while one is
    frontmost is the same risk class ``capture.py`` already refuses. A
    Stop click aborts this too — it was the only helper that kept
    working after the Working chip.
    """
    from AppKit import NSPasteboard, NSPasteboardTypeString
    from . import safety as _safety
    _gate()
    _safety.check_frontmost_allowed()
    pb = NSPasteboard.generalPasteboard()
    val = pb.stringForType_(NSPasteboardTypeString)
    out = str(val) if val else ""
    # Length only — never the contents.
    _safety.audit("clipboard_get", {"n": len(out)})
    return out


def clipboard_set(text: str) -> None:
    """Put plain text on the Mac clipboard."""
    from AppKit import NSPasteboard, NSPasteboardTypeString
    from . import safety as _safety
    _gate()
    _safety.check_frontmost_allowed()
    _safety.audit("clipboard_set", {"n": len(text)})
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    if not pb.setString_forType_(str(text), NSPasteboardTypeString):
        raise RuntimeError("clipboard_set failed")


def ensure_daemon() -> bool:
    """Return True if warm daemon is available (start is a separate CLI step)."""
    from . import daemon as d
    return d.is_running()


def run_plan(
    steps: list[dict[str, Any]],
    *,
    stop_on_error: bool = True,
    app: str | int | None = None,
) -> list[dict[str, Any]]:
    """Run many UI steps in **one process** (daemon-friendly, low round-trips).

    Prefer this over N separate ``desktop-harness`` CLI calls for a multi-step
    task — same capability, far less spawn/IPC cost.

    Each step is a dict with ``"op"`` plus op-specific fields:

    | op | fields |
    |----|--------|
    | ``open_app`` | ``name`` |
    | ``click`` | ``x``, ``y`` (global) or ``wx``, ``wy`` (window-local) |
    | ``drag`` | ``x1,y1,x2,y2`` or ``wx1,wy1,wx2,wy2`` |
    | ``click_text`` | ``text``, optional ``app``, ``exact`` |
    | ``type_text`` | ``text`` |
    | ``hotkey`` | ``keys`` (list) |
    | ``key`` | ``name`` |
    | ``wait`` | ``seconds`` |
    | ``screenshot`` | optional ``app`` |
    | ``labels`` | optional ``app``, ``limit`` |
    | ``hide_presence`` | — |

    When ``app`` is set on the plan, window-local coords use that frame once
    (cached for the whole plan). Returns a list of ``{op, ok, result|error}``.
    """
    results: list[dict[str, Any]] = []
    frame: dict[str, Any] | None = None
    plan_app = app

    def _frame_for(step_app=None):
        nonlocal frame, plan_app
        a = step_app if step_app is not None else plan_app
        if a is None and frame is None:
            try:
                frame = window_frame(None)
            except Exception:
                frame = None
            return frame
        if a is not None:
            return window_frame(a)
        return frame

    for i, raw in enumerate(steps):
        _gate()
        step = dict(raw or {})
        op = (step.get("op") or step.get("action") or "").strip().lower()
        entry: dict[str, Any] = {"i": i, "op": op, "ok": False}
        try:
            if op in ("open_app", "open"):
                entry["result"] = open_app(step["name"])
            elif op == "open_stage":
                entry["result"] = open_stage(step.get("url"))
            elif op == "close_stage":
                entry["result"] = close_stage()
            elif op == "show_monitor":
                entry["result"] = show_monitor()
            elif op == "hide_monitor":
                hide_monitor()
                entry["result"] = True
            elif op == "stage_note":
                entry["result"] = stage_note(step.get("text") or step.get("note") or "")
            elif op == "follow":
                entry["result"] = follow(
                    step.get("app"), window_id=step.get("window_id")
                )
            elif op == "click":
                if "wx" in step or "wy" in step:
                    fr = _frame_for(step.get("app"))
                    entry["result"] = click_in_window(
                        float(step.get("wx", 0)),
                        float(step.get("wy", 0)),
                        step.get("app", plan_app),
                        frame=fr,
                    )
                else:
                    entry["result"] = click(float(step["x"]), float(step["y"]))
            elif op == "drag":
                if "wx1" in step or "wy1" in step:
                    fr = _frame_for(step.get("app"))
                    entry["result"] = drag_in_window(
                        float(step.get("wx1", 0)),
                        float(step.get("wy1", 0)),
                        float(step.get("wx2", 0)),
                        float(step.get("wy2", 0)),
                        step.get("app", plan_app),
                        frame=fr,
                    )
                else:
                    entry["result"] = drag(
                        float(step["x1"]), float(step["y1"]),
                        float(step["x2"]), float(step["y2"]),
                    )
            elif op == "click_text":
                entry["result"] = click_text(
                    step["text"],
                    app=step.get("app", plan_app),
                    exact=bool(step.get("exact", False)),
                )
            elif op == "type_text":
                entry["result"] = type_text(step["text"])
            elif op == "hotkey":
                keys = step.get("keys") or step.get("key") or []
                if isinstance(keys, str):
                    keys = keys.split("+")
                entry["result"] = hotkey(*keys)
            elif op == "key":
                entry["result"] = key(step.get("name") or step.get("key"))
            elif op == "wait":
                wait(float(step.get("seconds", step.get("s", 0.3))))
                entry["result"] = {"waited": step.get("seconds", 0.3)}
            elif op == "screenshot":
                entry["result"] = str(
                    screenshot(app=step.get("app", plan_app))
                )
            elif op == "labels":
                entry["result"] = labels(
                    step.get("app", plan_app),
                    limit=int(step.get("limit", 30)),
                )
            elif op in ("hide_presence", "hide_agent_presence"):
                hide_agent_presence()
                entry["result"] = True
            elif op == "window_frame":
                entry["result"] = window_frame(step.get("app", plan_app))
            elif op == "menu_click":
                p = step.get("path") or step.get("items") or []
                if isinstance(p, str):
                    p = [p]
                entry["result"] = menu_click(*p, app=step.get("app", plan_app))
            elif op == "wait_for":
                entry["result"] = wait_for(
                    step.get("text") or step.get("name") or "",
                    app=step.get("app", plan_app),
                    role=step.get("role"),
                    exact=bool(step.get("exact", False)),
                    timeout=float(step.get("timeout", 3.0)),
                )
            elif op == "clipboard_get":
                entry["result"] = clipboard_get()
            elif op == "clipboard_set":
                clipboard_set(step.get("text") or "")
                entry["result"] = True
            else:
                raise ValueError(f"unknown plan op: {op!r}")
            entry["ok"] = True
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
            results.append(entry)
            if stop_on_error:
                break
            continue
        results.append(entry)
    return results


def button_labels(app: str | int | None = None, limit: int = 40) -> list[str]:
    """Labels of visible buttons only (handy for player/toolbars)."""
    nodes = ax_snapshot(app, max_nodes=300, interactive_only=True)
    out, seen = [], set()
    for n in nodes:
        if n.get("role") != "AXButton":
            continue
        lab = (n.get("label") or n.get("title") or "").strip()
        if not lab or lab in seen:
            continue
        seen.add(lab)
        out.append(lab)
        if len(out) >= limit:
            break
    return out


def _media_state_from_nodes(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Shared scoring logic for media_transport()/ensure_media_playing() —
    keeps both reading from one already-fetched node list instead of each
    re-walking the AX tree. Includes an internal "_play_el" (stripped by
    media_transport's public return) so ensure_media_playing can press the
    transport button it just found without a second find()/AXPress walk."""
    labs = []
    has_pause = has_transport_play = has_row_play = False
    play_el = None
    for n in nodes:
        if n.get("role") != "AXButton":
            continue
        lab = (n.get("label") or n.get("title") or "").strip()
        if not lab:
            continue
        labs.append(lab)
        low = lab.lower()
        if low == "pause" or low.startswith("pause "):
            has_pause = True
        elif low == "play":
            has_transport_play = True
            if play_el is None:
                play_el = n.get("_el")
        elif (low.startswith("play ")
              and "playlist" not in low
              and "play all" not in low
              and "playing" not in low):
            # "Play <track>" row buttons — not the main transport
            has_row_play = True
    # State is driven by transport controls only
    if has_pause and not has_transport_play:
        state = "playing"
    elif has_transport_play and not has_pause:
        state = "paused"
    elif has_pause and has_transport_play:
        # both visible rare; trust Pause
        state = "playing"
    else:
        state = "unknown"
    return {
        "state": state,
        "pause": has_pause,
        "play": has_transport_play,  # transport only (API stable)
        "transport_play": has_transport_play,
        "row_play": has_row_play,
        "labels": labs[:30],
        "_play_el": play_el,
    }


def media_transport(app: str | int | None = None) -> dict[str, Any]:
    """Inspect Play/Pause transport without clicking.

    Returns {state: 'playing'|'paused'|'unknown', pause: bool, play: bool,
             transport_play: bool, row_play: bool, labels: [...]}

    Transport Play = exact label "Play" (player bar).
    Row Play = "Play <track name>" list rows (does NOT mean paused).
    Prefer this before any media click. Never spam Space — it toggles.
    """
    nodes = ax_snapshot(app, max_nodes=400, interactive_only=True)
    status = _media_state_from_nodes(nodes)
    status.pop("_play_el", None)
    return status


def ensure_media_playing(app: str | int | None = None) -> dict[str, Any]:
    """If transport shows Pause, do nothing. If Play, press it once.

    Order (no thrash — one path only):
      1. AX: Pause visible → already playing → noop
      2. AX: exact Play button → press once → re-read
      3. Web/Electron fallback: system ``media_key('playpause')`` once when
         AX has no transport (YT Music Safari Web App, etc.)

    Never spam Space. Never multi-retry in one call.
    """
    from . import safety as _safety
    _gate()
    nodes = ax_snapshot(app, max_nodes=400, interactive_only=True, include_el=True)
    status = _media_state_from_nodes(nodes)
    play_el = status.pop("_play_el", None)
    _safety.audit("ensure_media_playing", status)
    if status["state"] == "playing":
        return {"action": "noop", **status}
    if status["state"] == "paused":
        # Same gate click_text() would apply — direct-press must not
        # bypass the sensitive-app mutation check.
        _safety.check_frontmost_allowed()
        if app:
            _safety.check_app_allowed(str(app))
        pressed = False
        hit: dict[str, Any] = {"label": "Play", "role": "AXButton"}
        if play_el is not None:
            _safety.audit("click_text", {"text": "Play", "app": app, "exact": True, "direct": True})
            pressed = _ax.press_element(play_el)
        if not pressed:
            # Element missing/stale/press failed — fall back to the normal
            # find()+click_text path (it does its own fresh walk).
            hit = click_text("Play", app=app, role="AXButton", exact=True)
        wait_stable(0.3)
        again = media_transport(app)
        return {"action": "pressed_play", "before": status, "after": again, "hit": hit}

    # Unknown: web apps often expose zero Play/Pause labels. One media-key
    # pulse is the capable path without thrashing AX or Space.
    _safety.check_frontmost_allowed()
    if app is not None:
        _safety.check_app_allowed(str(app))
        # Focus the player so the media key reaches it when possible
        try:
            if isinstance(app, int):
                info = find_app(app)
                if info and info.get("name"):
                    open_app(info["name"])
            else:
                open_app(str(app))
            wait_stable(0.15)
        except Exception:
            pass
    media_key("playpause")
    wait_stable(0.4)
    again = media_transport(app)
    return {
        "action": "media_key_playpause",
        "before": status,
        "after": again,
        "note": (
            "AX had no Play/Pause (common for YT Music web app). "
            "Sent one system media-key. If still silent, click the on-screen "
            "Play with click_in_window after a screenshot."
        ),
    }


def click_text(
    text: str,
    app: str | int | None = None,
    *,
    role: str | None = None,
    prefer_ax_press: bool = True,
    exact: bool = False,
) -> dict[str, Any]:
    """Find best match and activate it (AXPress preferred, else click center).

    exact=True: only accept title/label equal to text (case-insensitive).
    Prefer role=\"AXButton\" for toolbar/player controls.
    """
    from . import safety as _safety
    _gate()
    _safety.check_frontmost_allowed()
    if app:
        _safety.check_app_allowed(str(app))
    _safety.audit("click_text", {"text": text, "app": app, "exact": exact})
    hits = _ax.find(text, app=app, role=role, max_results=12, include_el=True)
    if exact:
        q = text.strip().lower()
        hits = [
            h for h in hits
            if (h.get("title") or "").strip().lower() == q
            or (h.get("label") or "").strip().lower() == q
        ]
    if not hits:
        # show what's visible to help the agent
        sample = _ax.public_nodes(
            _ax.ax_snapshot(app, max_nodes=40, interactive_only=True, include_el=True))
        labels = [n.get("label") or n.get("title") or n.get("role") for n in sample[:25]]
        raise RuntimeError(
            f"no AX match for {text!r} (role={role!r}, exact={exact}). visible sample: {labels}")
    hit = _pick_click_hit(hits, text)
    el = hit.get("_el")
    role_name = hit.get("role") or ""
    if prefer_ax_press and el is not None and _ax_pressable(role_name):
        if _ax.press_element(el):
            wait_stable()
            return {k: v for k, v in hit.items() if not k.startswith("_")}
    frame = hit.get("frame")
    if not frame:
        raise RuntimeError(f"matched {text!r} but no frame and AXPress failed: {hit}")
    if not _frame_is_click_target(hit):
        raise RuntimeError(
            f"refusing to click {text!r}: match is {role_name} "
            f"{int(frame.get('w', 0))}×{int(frame.get('h', 0))} — "
            f"too large / not a control. Name a button or pass exact=True."
        )
    # ensure app frontmost for coordinate click
    if app is not None:
        try:
            if isinstance(app, int):
                # pid → resolve name, then activate
                from AppKit import NSRunningApplication
                ra = NSRunningApplication.runningApplicationWithProcessIdentifier_(app)
                name = (ra.localizedName() if ra else None) or "Finder"
                activate(name)
            else:
                activate(str(app))
        except Exception:
            pass
    click_frame(frame)
    wait_stable()
    return {k: v for k, v in hit.items() if not k.startswith("_")}


_PRESSABLE = frozenset({
    "AXButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton",
    "AXMenuButton", "AXMenuItem", "AXLink", "AXTab",
    "AXDisclosureTriangle", "AXComboBox", "AXMenuBarItem",
})
_CONTAINERS = frozenset({
    "AXWindow", "AXGroup", "AXScrollArea", "AXSplitGroup",
    "AXList", "AXOutline", "AXTable", "AXLayoutArea",
    "AXBrowser", "AXWebArea", "AXSheet", "AXDialog",
})
_MIN_CLICK_SCORE = 60


def _ax_pressable(role: str) -> bool:
    return role in _PRESSABLE


def _frame_is_click_target(hit: dict[str, Any]) -> bool:
    """True only if a coordinate click on this hit is a real control.

    Clicking the center of a window / group / web area is the usual
    accidental click. Buttons may be wide; containers may not.
    """
    role = hit.get("role") or ""
    fr = hit.get("frame") or {}
    w = float(fr.get("w") or 0)
    h = float(fr.get("h") or 0)
    if w <= 0 or h <= 0:
        return False
    if role in _PRESSABLE:
        return True
    if role in _CONTAINERS:
        return False
    # Labels / unknown: only if they look like a control, not a paragraph.
    return w * h <= 24000 and w <= 420 and h <= 120


def _pick_click_hit(hits: list[dict[str, Any]], text: str) -> dict[str, Any]:
    """Fail closed: weak or neck-and-neck matches are not clicked."""
    confident = [h for h in hits if float(h.get("score") or 0) >= _MIN_CLICK_SCORE]
    pool = confident or hits
    hit = pool[0]
    if float(hit.get("score") or 0) < _MIN_CLICK_SCORE:
        names = [
            (h.get("label") or h.get("title") or h.get("role"), h.get("score"))
            for h in hits[:4]
        ]
        raise RuntimeError(
            f"refusing to click {text!r}: no confident match {names}. "
            f"Be more specific or pass exact=True."
        )
    if len(pool) >= 2:
        s0 = float(pool[0].get("score") or 0)
        s1 = float(pool[1].get("score") or 0)
        if s0 - s1 < 12:
            a = pool[0].get("label") or pool[0].get("title")
            b = pool[1].get("label") or pool[1].get("title")
            if (a or "").strip().lower() != (b or "").strip().lower():
                raise RuntimeError(
                    f"refusing to click {text!r}: ambiguous "
                    f"{a!r} ({s0:.0f}) vs {b!r} ({s1:.0f}). "
                    f"Pass exact=True or a longer name."
                )
    return hit


def set_field(text: str, value: str, app: str | int | None = None) -> dict[str, Any]:
    """Find a text field by nearby label/title and set its value."""
    from . import safety as _safety
    # Same gate click_text applies. Without it the AX set_value path below wrote
    # into a focused field with no check and no audit row, while the slower
    # click+type fallback underneath it was gated — so the fast path was the
    # unguarded one.
    _gate()
    _safety.check_frontmost_allowed()
    if app:
        _safety.check_app_allowed(str(app))
    _safety.audit("set_field", {"text": text, "app": app, "n": len(value)})
    hits = _ax.find(text, app=app, max_results=10, include_el=True)
    # prefer text fields
    ordered = sorted(
        hits,
        key=lambda h: (0 if "Text" in (h.get("role") or "") else 1, -h.get("score", 0)),
    )
    if not ordered:
        raise RuntimeError(f"no field matching {text!r}")
    hit = ordered[0]
    el = hit.get("_el")
    if el is not None and _ax.set_value(el, value):
        wait_stable()
        return {k: v for k, v in hit.items() if not k.startswith("_")}
    # fallback: click + type
    if hit.get("frame"):
        click_frame(hit["frame"])
        wait(0.15)
        hotkey("cmd", "a")
        type_text(value)
        wait_stable()
        return {k: v for k, v in hit.items() if not k.startswith("_")}
    raise RuntimeError(f"could not set field {text!r}")


def labels(app: str | int | None = None, limit: int = 40) -> list[str]:
    """Quick list of visible labels for debugging."""
    nodes = ax_snapshot(app, max_nodes=limit * 3, interactive_only=True)
    out = []
    seen = set()
    for n in nodes:
        lab = (n.get("label") or "").strip()
        if not lab or lab in seen:
            continue
        seen.add(lab)
        out.append(f"{n.get('role','')}: {lab}")
        if len(out) >= limit:
            break
    return out


def screen_info(app: str | None = None) -> dict[str, Any]:
    front = frontmost_app()
    wins = list_windows()
    if app:
        wins = [w for w in wins if app.lower() in w["app"].lower()]
    return {
        "frontmost": front,
        "windows": wins[:12],
        "window_count": len(wins),
    }


def verify(note: str = "", app: str | int | None = None) -> dict[str, Any]:
    """Screenshot + AX read to close the loop on an action whose failure
    would otherwise be silent — NOT a routine step after every click.

    click_text/set_field already raise if there's no AX match; that's the
    check for ordinary UI changes. Reach for this specifically for actions
    that can succeed at the AX layer while doing the wrong thing with no
    other way to notice — media transport toggles, anything gated under
    the Consent section, a step you're about to report as finished where
    being wrong matters. Calling it after everything reintroduces the
    vision-loop tax the rest of this module exists to avoid. When you do
    call it, Read the screenshot path it returns before deciding the step
    succeeded — the point is looking, not just calling the function.

    `note` is free text describing what you expected to happen — it goes
    into the audit log next to the actual state, so a later pass (by you
    or another agent) can compare intent vs. outcome without re-deriving
    context.
    """
    result: dict[str, Any] = {"note": note}
    try:
        result["frontmost"] = frontmost_app()
    except Exception as e:
        result["frontmost_error"] = str(e)
    try:
        result["labels"] = labels(app, limit=25)
    except Exception as e:
        result["labels_error"] = str(e)
    try:
        result["screenshot"] = screenshot(app=app if isinstance(app, str) else None)
    except Exception as e:
        result["screenshot_error"] = str(e)
    try:
        from . import safety as _safety
        _safety.audit("verify", {"note": note, "app": app,
                                  "frontmost": result.get("frontmost")})
    except Exception:
        pass
    return result


def _load_agent_helpers():
    p = AGENT_WORKSPACE / "agent_helpers.py"
    if not p.exists():
        return {}
    spec = importlib.util.spec_from_file_location("desktop_harness_agent_helpers", p)
    if spec is None or spec.loader is None:
        return {}
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {k: getattr(mod, k) for k in dir(mod) if not k.startswith("_")}


def namespace() -> dict[str, Any]:
    """Globals injected into scripts."""
    ns = {k: v for k, v in globals().items() if not k.startswith("_")}
    ns.update(_load_agent_helpers())
    return ns
