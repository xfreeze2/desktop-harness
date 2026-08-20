"""HID-level mouse and keyboard via CGEvent.

Mouse control is real system-cursor control:
  - CGWarpMouseCursorPosition moves the *visible* pointer
  - CGEventPost delivers clicks/drags/keys apps actually receive
"""
from __future__ import annotations

import math
import time
from typing import Any

import Quartz

# Keycodes (US layout) for common chords.
# Aliases for symbols agents actually type ("-", "=", "[") so hotkey("cmd","-")
# never fails mid-task — missing keys were a real Canva zoom hiccup.
_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
    "3": 20, "4": 21, "6": 22, "5": 23, "equal": 24, "9": 25, "7": 26, "minus": 27,
    "8": 28, "0": 29, "o": 31, "u": 32, "i": 34, "p": 35, "return": 36, "l": 37,
    "j": 38, "k": 40, "semicolon": 41, "n": 45, "m": 46, "tab": 48, "space": 49,
    "grave": 50, "delete": 51, "escape": 53, "command": 55, "shift": 56,
    "option": 58, "control": 59, "right": 124, "left": 123, "down": 125, "up": 126,
    "cmd": 55, "alt": 58, "ctrl": 59, "enter": 36, "esc": 53, "backspace": 51,
    # Symbol aliases (same physical keys as equal/minus)
    "-": 27, "=": 24, "+": 24,
    # Brackets / punctuation (layer shortcuts, send-backward chords, etc.)
    "[": 33, "]": 30, "bracketleft": 33, "bracketright": 30,
    "comma": 43, "period": 47, "slash": 44, "backslash": 42,
    ",": 43, ".": 47, "/": 44, "\\": 42,
    # Navigation
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "forwarddelete": 117, "fwddelete": 117,
}

# Optional agent presence overlay (ring + banner)
_overlay = None
_auto_presence = True  # wire presence module on first motion if enabled
_last_warp: tuple[float, float] | None = None
_HUMAN_MOVE_PX = 18.0


class PointerTaken(RuntimeError):
    """User moved the mouse — refuse to click over them."""


def set_overlay(overlay) -> None:
    """Attach visual presence (presence module)."""
    global _overlay
    _overlay = overlay


def _assert_running(*, pump: bool = True) -> None:
    """Honor a Stop click; surface the control chip on HID mutations.

    Without ensure(), AX-free paths that somehow skip helpers._gate would
    still drive the Mac with no visible Stop. Cheap when already active.
    """
    try:
        from . import presence
        if pump:
            try:
                presence.ensure()
            except Exception:
                pass
        presence.assert_running(pump=pump)
    except Exception as e:
        from .presence import ControlStopped
        if isinstance(e, ControlStopped):
            raise
        # Presence unavailable — still allow control.


def _presence_move(x: float, y: float):
    global _overlay
    if _overlay is not None:
        try:
            _overlay.move(x, y)
            return
        except Exception:
            pass
    if not _auto_presence:
        return
    try:
        from . import presence
        if presence.enabled():
            presence.ensure()
            presence.move(x, y)
            _overlay = presence
    except Exception:
        pass


def _presence_click(x: float, y: float):
    try:
        from . import presence
        if presence.enabled():
            presence.click_flash(x, y)
    except Exception:
        pass


def mouse_pos() -> dict[str, float]:
    """Current system pointer location in global screen points."""
    ev = Quartz.CGEventCreate(None)
    p = Quartz.CGEventGetLocation(ev)
    return {"x": float(p.x), "y": float(p.y)}


def _post_mouse(event_type: int, x: float, y: float, button=Quartz.kCGMouseButtonLeft):
    pt = Quartz.CGPointMake(float(x), float(y))
    ev = Quartz.CGEventCreateMouseEvent(None, event_type, pt, button)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def _warp(x: float, y: float):
    """Move the visible system cursor (what the human sees)."""
    global _last_warp
    Quartz.CGWarpMouseCursorPosition(Quartz.CGPointMake(float(x), float(y)))
    # Associate next mouse event with warp so apps don't jump-correct
    Quartz.CGAssociateMouseAndMouseCursorPosition(True)
    _last_warp = (float(x), float(y))
    _presence_move(x, y)


def human_is_driving() -> bool:
    """True if the pointer moved without us warping it — user has the mouse."""
    if _last_warp is None:
        return False
    p = mouse_pos()
    return math.hypot(p["x"] - _last_warp[0], p["y"] - _last_warp[1]) > _HUMAN_MOVE_PX


def _guard_click() -> None:
    """Fail closed: never click on top of a human who just moved the mouse."""
    if human_is_driving():
        raise PointerTaken(
            "refusing click: the pointer moved independently "
            "(you are using the mouse)"
        )


def move_to(
    x: float,
    y: float,
    *,
    duration: float = 0.08,
    steps: int | None = None,
) -> dict[str, float]:
    """Animate the real mouse pointer to (x, y). Returns final position.

    Defaults favor agent speed (short path). Use duration=0.3+ for visible demos.
    Set DH_MOUSE_INSTANT=1 to warp with zero animation.
    """
    import os
    _assert_running()
    if os.environ.get("DH_MOUSE_INSTANT", "").lower() in ("1", "true", "yes"):
        duration = 0
    start = mouse_pos()
    x0, y0 = start["x"], start["y"]
    dist = math.hypot(x - x0, y - y0)
    if dist < 2:
        _warp(x, y)
        _post_mouse(Quartz.kCGEventMouseMoved, x, y)
        return {"x": float(x), "y": float(y)}
    if steps is None:
        # fewer steps: ~1 per 20px, max 24
        steps = max(1, min(24, int(dist / 20) or 1))
    if duration <= 0 or steps <= 1:
        _warp(x, y)
        _post_mouse(Quartz.kCGEventMouseMoved, x, y)
        return {"x": float(x), "y": float(y)}
    dt = duration / steps
    for i in range(1, steps + 1):
        t = i / steps
        # ease-in-out
        te = t * t * (3 - 2 * t)
        xi = x0 + (x - x0) * te
        yi = y0 + (y - y0) * te
        _warp(xi, yi)
        _post_mouse(Quartz.kCGEventMouseMoved, xi, yi)
        time.sleep(dt)
        _assert_running()
    return {"x": float(x), "y": float(y)}


def move_by(dx: float, dy: float, **kwargs) -> dict[str, float]:
    p = mouse_pos()
    return move_to(p["x"] + dx, p["y"] + dy, **kwargs)


def wiggle(amplitude: float = 12.0, cycles: int = 2, duration: float = 0.35):
    """Small wiggle at current position — agent is thinking / about to act."""
    origin = mouse_pos()
    ox, oy = origin["x"], origin["y"]
    n = max(8, cycles * 8)
    dt = duration / n
    for i in range(n):
        ang = (i / n) * cycles * 2 * math.pi
        xi = ox + amplitude * math.sin(ang)
        yi = oy + amplitude * 0.4 * math.cos(ang)
        _warp(xi, yi)
        _post_mouse(Quartz.kCGEventMouseMoved, xi, yi)
        time.sleep(dt)
    _warp(ox, oy)
    _post_mouse(Quartz.kCGEventMouseMoved, ox, oy)
    return origin


def tap(x: float, y: float, *, double: bool = False) -> dict[str, float]:
    """Instant click. No pointer animation, no settle sleep.

    Use this inside a tight loop. Everyday ``click()`` still animates so
    a human can watch a one-off action.
    """
    _assert_running(pump=False)
    _guard_click()
    _warp(x, y)
    _post_mouse(Quartz.kCGEventMouseMoved, x, y)
    _guard_click()
    _post_mouse(Quartz.kCGEventLeftMouseDown, x, y)
    _post_mouse(Quartz.kCGEventLeftMouseUp, x, y)
    if double:
        _post_mouse(Quartz.kCGEventLeftMouseDown, x, y)
        _post_mouse(Quartz.kCGEventLeftMouseUp, x, y)
    return {"x": float(x), "y": float(y)}


def mouse_down(x: float, y: float) -> dict[str, float]:
    """Press and hold the left button at (x, y). Pair with mouse_up."""
    _assert_running(pump=False)
    _guard_click()
    _warp(x, y)
    _post_mouse(Quartz.kCGEventMouseMoved, x, y)
    _post_mouse(Quartz.kCGEventLeftMouseDown, x, y)
    return {"x": float(x), "y": float(y)}


def mouse_up(x: float | None = None, y: float | None = None) -> dict[str, float]:
    """Release the left button. Defaults to the current pointer."""
    if x is None or y is None:
        p = mouse_pos()
        x = p["x"] if x is None else x
        y = p["y"] if y is None else y
    _post_mouse(Quartz.kCGEventLeftMouseUp, float(x), float(y))
    return {"x": float(x), "y": float(y)}


def click(x: float, y: float, *, double: bool = False, settle: float = 0.04,
          move: bool = True, duration: float = 0.06):
    """Left click at global screen coordinates. Moves the real pointer first.

    duration default is short (0.06s) for agent speed; pass higher for demos.
    """
    _assert_running()
    _guard_click()
    if move:
        move_to(x, y, duration=duration)
    else:
        _warp(x, y)
        _post_mouse(Quartz.kCGEventMouseMoved, x, y)
    time.sleep(0.02)
    _guard_click()
    _presence_click(x, y)
    _post_mouse(Quartz.kCGEventLeftMouseDown, x, y)
    _post_mouse(Quartz.kCGEventLeftMouseUp, x, y)
    if double:
        time.sleep(0.05)
        _post_mouse(Quartz.kCGEventLeftMouseDown, x, y)
        _post_mouse(Quartz.kCGEventLeftMouseUp, x, y)
    time.sleep(settle)


def right_click(x: float, y: float, settle: float = 0.05, move: bool = True):
    _assert_running()
    _guard_click()
    if move:
        move_to(x, y, duration=0.12)
    else:
        _warp(x, y)
        _post_mouse(Quartz.kCGEventMouseMoved, x, y)
    time.sleep(0.02)
    _post_mouse(Quartz.kCGEventRightMouseDown, x, y, Quartz.kCGMouseButtonRight)
    _post_mouse(Quartz.kCGEventRightMouseUp, x, y, Quartz.kCGMouseButtonRight)
    time.sleep(settle)


def click_frame(frame: dict, *, double: bool = False):
    """Click center of {x,y,w,h}."""
    x = frame["x"] + frame["w"] / 2
    y = frame["y"] + frame["h"] / 2
    click(x, y, double=double)


def drag(x1: float, y1: float, x2: float, y2: float, steps: int = 20,
         duration: float = 0.35):
    """Drag with visible pointer motion."""
    _assert_running()
    _guard_click()
    move_to(x1, y1, duration=0.12)
    _post_mouse(Quartz.kCGEventLeftMouseDown, x1, y1)
    dt = duration / max(steps, 1)
    for i in range(1, steps + 1):
        t = i / steps
        te = t * t * (3 - 2 * t)
        x = x1 + (x2 - x1) * te
        y = y1 + (y2 - y1) * te
        _warp(x, y)
        pt = Quartz.CGPointMake(x, y)
        ev = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDragged, pt, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(dt)
        _assert_running()
    _post_mouse(Quartz.kCGEventLeftMouseUp, x2, y2)
    time.sleep(0.03)


def scroll(dx: int = 0, dy: int = 3, x: float | None = None, y: float | None = None):
    """Scroll wheel at optional location (moves pointer there first)."""
    _assert_running()
    if x is not None and y is not None:
        move_to(x, y, duration=0.1)
    ev = Quartz.CGEventCreateScrollWheelEvent(
        None, Quartz.kCGScrollEventUnitLine, 2, int(dy), int(dx))
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def _key_event(keycode: int, down: bool, flags: int = 0):
    ev = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
    if flags:
        Quartz.CGEventSetFlags(ev, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


_held_keys: set[str] = set()


def _code_for(name: str) -> int:
    code = _KEYCODES.get(name.lower())
    if code is None:
        raise ValueError(f"unknown key: {name!r}")
    return code


def key(name: str, *, settle: float = 0.03):
    """Press a named key (return, escape, tab, …)."""
    _assert_running()
    _key_event(_code_for(name), True)
    _key_event(_code_for(name), False)
    time.sleep(settle)


def key_down(name: str) -> str:
    """Hold a key down. Pair with key_up / keys_hold. No settle sleep."""
    _assert_running(pump=False)
    n = name.lower()
    if n not in _held_keys:
        _key_event(_code_for(n), True)
        _held_keys.add(n)
    return n


def key_up(name: str) -> str:
    """Release a held key."""
    n = name.lower()
    if n in _held_keys:
        try:
            _key_event(_code_for(n), False)
        except Exception:
            pass
        _held_keys.discard(n)
    return n


def keys_hold(names: list[str] | set[str] | tuple[str, ...] | None = None) -> list[str]:
    """Make *exactly* these keys be down. Releases anything else we held.

    Hold W and release S in one call — no tap-gap. Same primitive for
    a game, a video scrub, or any key that must stay down.
    """
    _assert_running(pump=False)
    want = {str(n).lower() for n in (names or [])}
    for n in list(_held_keys - want):
        key_up(n)
    for n in want - _held_keys:
        key_down(n)
    return sorted(_held_keys)


def release_keys() -> None:
    """Release every key this process is holding. Safe in finally/Stop."""
    for n in list(_held_keys):
        try:
            _key_event(_code_for(n), False)
        except Exception:
            pass
    _held_keys.clear()


def held_keys() -> list[str]:
    return sorted(_held_keys)


def hotkey(*keys: str, settle: float = 0.05):
    """Chord like hotkey('cmd', 's') or hotkey('cmd', 'shift', 't')."""
    _assert_running()
    parts = [k.lower() for k in keys]
    flags = 0
    mods = []
    if "cmd" in parts or "command" in parts:
        flags |= Quartz.kCGEventFlagMaskCommand
        mods.append(_KEYCODES["cmd"])
    if "shift" in parts:
        flags |= Quartz.kCGEventFlagMaskShift
        mods.append(_KEYCODES["shift"])
    if "alt" in parts or "option" in parts:
        flags |= Quartz.kCGEventFlagMaskAlternate
        mods.append(_KEYCODES["option"])
    if "ctrl" in parts or "control" in parts:
        flags |= Quartz.kCGEventFlagMaskControl
        mods.append(_KEYCODES["control"])
    main = [p for p in parts if p not in {
        "cmd", "command", "shift", "alt", "option", "ctrl", "control"}]
    if not main:
        raise ValueError("hotkey needs a non-modifier key")
    main_code = _KEYCODES.get(main[-1])
    if main_code is None:
        # single character
        ch = main[-1]
        if len(ch) == 1:
            main_code = _KEYCODES.get(ch.lower())
        if main_code is None:
            raise ValueError(f"unknown key in hotkey: {main[-1]!r}")
    for m in mods:
        _key_event(m, True, flags)
    _key_event(main_code, True, flags)
    _key_event(main_code, False, flags)
    for m in reversed(mods):
        _key_event(m, False, flags)
    time.sleep(settle)


# System media keys (NX_KEYTYPE_*) — work for Music, YT Music web apps, etc.
# when AX exposes no Play/Pause control.
_MEDIA_KEYCODES = {
    "play": 16,
    "playpause": 16,
    "next": 17,
    "previous": 18,
    "prev": 18,
    "fast": 19,
    "rewind": 20,
    "volumeup": 0,
    "volup": 0,
    "volumedown": 1,
    "voldown": 1,
    "mute": 7,
}


def media_key(name: str = "playpause", *, settle: float = 0.05) -> str:
    """Post a system media key (play/pause, next, previous).

    Use when the player is a web view / Electron app with no AX Play button
    (YT Music Safari Web App is the classic case). Prefer
    ``ensure_media_playing`` first for native AX players.
    """
    _assert_running()
    code = _MEDIA_KEYCODES.get(name.lower().strip())
    if code is None:
        raise ValueError(
            f"unknown media key {name!r}; expected one of {sorted(_MEDIA_KEYCODES)}"
        )
    # NSEvent system-defined media-key packet → CGEvent
    try:
        from AppKit import NSEvent, NSSystemDefined
    except ImportError as e:
        raise RuntimeError("AppKit required for media_key") from e

    for down in (True, False):
        flags = 0xA00 if down else 0xB00
        data1 = (code << 16) | ((0xA if down else 0xB) << 8)
        ev = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            NSSystemDefined,
            (0.0, 0.0),
            flags,
            0,
            0,
            None,
            8,  # subtype: system-defined media
            data1,
            -1,
        )
        if ev is None:
            raise RuntimeError("failed to create media key NSEvent")
        cge = ev.CGEvent()
        if cge is None:
            raise RuntimeError("failed to get CGEvent from media key NSEvent")
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, cge)
        time.sleep(0.02)
    time.sleep(settle)
    return name


def type_text(text: str, *, delay: float = 0.008, paste_above: int = 48):
    """Type unicode via CGEvent keyboard with unicode string.

    Long strings paste via clipboard (cmd+v) — same capability, far less
    per-character HID cost. Short strings still key-by-key so apps that
    watch individual key events keep working. ``paste_above=0`` forces
    key-by-key always.
    """
    _assert_running()
    if paste_above and len(text) >= int(paste_above) and "\n" not in text and "\t" not in text:
        # Preserve prior clipboard; restore after paste.
        try:
            from AppKit import NSPasteboard, NSPasteboardTypeString
            pb = NSPasteboard.generalPasteboard()
            prev = pb.stringForType_(NSPasteboardTypeString)
            prev = str(prev) if prev else None
            pb.clearContents()
            if not pb.setString_forType_(text, NSPasteboardTypeString):
                raise RuntimeError("clipboard paste path failed")
            hotkey("cmd", "v", settle=0.04)
            if prev is not None:
                pb.clearContents()
                pb.setString_forType_(prev, NSPasteboardTypeString)
            return
        except Exception:
            # Fall through to per-char typing.
            pass
    for i, ch in enumerate(text):
        if ch == "\n":
            key("return")
            continue
        if ch == "\t":
            key("tab")
            continue
        # Unicode input
        ev_down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(ev_down, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_down)
        ev_up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(ev_up, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_up)
        if delay:
            time.sleep(delay)
        if i % 8 == 7:
            _assert_running()
