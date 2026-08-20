"""In-process see→act. Task-agnostic.

A chat turn is hundreds of milliseconds to several seconds. Anything that
must land on *this* frame (a game, a video cue, a scroll that has to hit
now) cannot wait for another model call. This module keeps capture and
input in one process and runs a policy the caller wrote.

Nothing here knows what app it is looking at. The policy does.
The harness only:

  1. grabs a RAM frame
  2. calls ``step(frame)``
  3. applies the action dict that comes back
  4. honors Stop and always releases keys

Write the policy in the script. Do not put app logic in this package.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from . import capture as _capture
from . import input as _input
from . import presence as _presence
from . import windows as _windows


def apply(action: Any, *, frame: dict[str, Any] | None = None) -> Any:
    """Apply one action dict. Unknown keys are ignored.

    | key | meaning |
    |-----|---------|
    | ``hold`` | ``keys_hold(list)`` — these keys down, others up |
    | ``key`` | tap a named key once |
    | ``tap`` | instant click, global ``[x, y]`` |
    | ``tap_win`` | instant click, window-local ``[x, y]`` (needs frame) |
    | ``move`` | warp pointer, global ``[x, y]`` |
    | ``scroll`` | ``[dx, dy]`` wheel ticks |
    | ``stop`` | end the loop (applied by ``run_loop``) |

    Returning ``None`` / ``{}`` does nothing. Returning a list applies
    each item in order.
    """
    if action is None:
        return None
    if isinstance(action, (list, tuple)):
        for item in action:
            apply(item, frame=frame)
        return action
    if not isinstance(action, dict):
        return action
    if "hold" in action:
        names = action["hold"]
        if names is None:
            names = []
        elif isinstance(names, str):
            names = [names]
        _input.keys_hold(names)
    if "key" in action and action["key"]:
        _input.key(str(action["key"]), settle=float(action.get("settle", 0.0)))
    if "tap" in action and action["tap"] is not None:
        x, y = action["tap"][0], action["tap"][1]
        _input.tap(float(x), float(y), double=bool(action.get("double")))
    if "tap_win" in action and action["tap_win"] is not None and frame is not None:
        wx, wy = action["tap_win"][0], action["tap_win"][1]
        gx = float(frame.get("x") or 0) + float(wx)
        gy = float(frame.get("y") or 0) + float(wy)
        _input.tap(gx, gy, double=bool(action.get("double")))
    if "move" in action and action["move"] is not None:
        x, y = action["move"][0], action["move"][1]
        _input.move_to(float(x), float(y), duration=0)
    if "scroll" in action and action["scroll"] is not None:
        dx, dy = action["scroll"][0], action["scroll"][1]
        _input.scroll(int(dx), int(dy))
    return action


def run_loop(
    step: Callable[[dict[str, Any]], Any],
    *,
    app: str | int | None = None,
    window_id: int | None = None,
    hz: float = 30.0,
    seconds: float = 12.0,
    max_frames: int | None = None,
    apply_actions: bool = True,
    on_stop: str = "release",
) -> dict[str, Any]:
    """Call ``step(frame)`` at ``hz`` until time / frames / Stop / stop.

    ``step`` receives a RAM frame from ``grab_frame``. Return an action
    dict (see ``apply``) or ``{"stop": True}`` to end.

    Do **not** call ``screenshot()`` or write files inside ``step``.
    Disk PNG is 10–50× slower than ``grab_frame`` and will miss the
    frame you meant to act on.

    Presence is polled so the Working · Stop chip still aborts.
    Held keys are released in ``finally``.
    """
    from .presence import ControlStopped as _CS

    hz = max(4.0, min(float(hz), 90.0))
    period = 1.0 / hz
    deadline = time.monotonic() + max(0.05, float(seconds))
    frames = 0
    last: Any = None
    t0 = time.monotonic()
    last_pump = 0.0
    wid = int(window_id) if window_id is not None else None
    app_name = None if isinstance(app, int) else app

    # Surface Stop before the first frame — tap/hold use pump=False.
    try:
        _presence.ensure()
        if app_name:
            _presence.set_driven(str(app_name))
            _presence.ring_window(app_name)
    except Exception:
        pass

    try:
        while time.monotonic() < deadline:
            if max_frames is not None and frames >= max_frames:
                break
            if _presence.stopped():
                raise _CS("user stopped desktop-harness from the Working chip")
            now = time.monotonic()
            if now - last_pump > 0.08:
                _presence.poll(deep=False)
                last_pump = now
                if _presence.stopped():
                    raise _CS("user stopped desktop-harness from the Working chip")

            if wid is None and app_name:
                try:
                    fr = _windows.window_frame(app_name)
                    wid = int(fr["id"])
                except Exception:
                    pass
            try:
                frame = _capture.grab_frame(app=app_name, window_id=wid)
            except RuntimeError:
                wid = None
                _windows._invalidate_window_cache()
                if app_name:
                    fr = _windows.window_frame(app_name)
                    wid = int(fr["id"])
                    frame = _capture.grab_frame(app=app_name, window_id=wid)
                else:
                    frame = _capture.grab_frame()
            frame["i"] = frames
            frame["t"] = now - t0
            last = step(frame)
            frames += 1
            if apply_actions:
                apply(last, frame=frame)
            if isinstance(last, dict) and last.get("stop"):
                break
            slept = time.monotonic() - now
            remain = period - slept
            # Chunked sleep so Stop still lands between frames when hz is low.
            while remain > 0.001:
                if _presence.stopped():
                    raise _CS("user stopped desktop-harness from the Working chip")
                chunk = min(0.05, remain)
                time.sleep(chunk)
                remain -= chunk
                if remain > 0.02:
                    _presence.poll(deep=False)
    finally:
        if on_stop == "release":
            _input.release_keys()

    elapsed = time.monotonic() - t0
    return {
        "frames": frames,
        "seconds": elapsed,
        "hz": (frames / elapsed) if elapsed > 0 else 0.0,
        "last": last,
    }
