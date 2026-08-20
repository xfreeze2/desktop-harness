"""Agent presence — one real cursor + synced glow (no second arrow).

Design rules (from observe loop):
  - NEVER draw a second pointer shape (dual-cursor lag is unusable)
  - System cursor stays; we only draw a soft HALO locked to the warp target
  - Move = cool ice ring; click = brief amber flash, then ice again
  - Control session chip: status + explicit Stop (not one ambiguous label)
  - Chip sits outside the driven window; only the Stop zone is hittable

DH_PRESENCE=0 disables everything.
"""
from __future__ import annotations

import os
import time
from typing import Any

_halo = None
_banner = None
_frame = None  # ice border around the window being driven
_app = None
_active = False
_last_cg: tuple[float, float] | None = None
_mode = "blue"  # blue | red
_frame_target: tuple[float, float, float, float] | None = None  # x,y,w,h CG
_stopped = False
_stop_source: str | None = None
_driven_label: str = ""  # short name shown on the chip
_session_t0: float = 0.0
_pip_phase: int = 0


class ControlStopped(RuntimeError):
    """User took the Mac back — Stop on the control chip was clicked."""

# Grok ice — same family as the cursor halo
_ICE = (0.45, 0.78, 1.00)

# IMPORTANT — main thread only. AppKit asserts on non-main-thread window
# calls and hard-aborts the whole process (SIGABRT, unrecoverable, no
# Python exception to catch) — verified by trying a background "keepalive"
# thread here and watching it crash desktop-harness every single run. Do
# not reach for threading to solve idle-persistence; use keep_alive()
# below to pump in small increments from whatever thread is already
# calling into presence (which must be the main thread).

# Halo canvas — circle centered on cursor tip
_SIZE = 52.0
_FLASH = 62.0


def enabled() -> bool:
    v = os.environ.get("DH_PRESENCE", "1").lower()
    return v not in ("0", "false", "no", "off")


def stopped() -> bool:
    """True after the user clicks Stop on the Working chip."""
    return _stopped


def clear_stop() -> None:
    """Allow control again. Only call when the user asked to continue."""
    global _stopped, _stop_source
    _stopped = False
    _stop_source = None


def request_stop(source: str = "chip") -> None:
    """Abort agent control. Safe to call from AppKit mouseDown."""
    global _stopped, _stop_source
    _stopped = True
    _stop_source = source
    try:
        from . import safety as _safety
        _safety.audit("user_stop", {"source": source})
    except Exception:
        pass
    hide()
    try:
        from . import stage as _stage
        _stage.hide_monitor()
    except Exception:
        pass
    try:
        from . import input as _input
        _input.set_overlay(None)
    except Exception:
        pass


def poll(*, deep: bool = False) -> None:
    """Pump AppKit so a Stop click is delivered. No-op if nothing is up."""
    if _app is None and not _active:
        return
    if deep:
        _pump(n=6, seconds=0.014)
    else:
        _pump(n=2, seconds=0.004)


def assert_running(*, pump: bool = True) -> None:
    """Raise ControlStopped if the user clicked Stop."""
    if pump:
        poll(deep=False)
    if _stopped:
        raise ControlStopped(
            "user stopped desktop-harness from the Working chip"
        )


def _ensure_app():
    global _app
    if _app is not None:
        return _app
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
    _app = NSApplication.sharedApplication()
    try:
        _app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass
    try:
        _app.finishLaunching()
    except Exception:
        pass
    return _app


def _pump(n: int = 4, seconds: float = 0.01):
    try:
        from AppKit import NSDate, NSDefaultRunLoopMode
        app = _ensure_app()
        deadline = time.time() + seconds
        i = 0
        while i < n and time.time() < deadline:
            ev = app.nextEventMatchingMask_untilDate_inMode_dequeue_(
                (1 << 64) - 1,
                NSDate.dateWithTimeIntervalSinceNow_(0.0004),
                NSDefaultRunLoopMode,
                True,
            )
            if ev is not None:
                app.sendEvent_(ev)
            i += 1
    except Exception:
        pass


def _style_panel(panel, boost: int = 0, click_through: bool = True):
    from AppKit import NSColor, NSPopUpMenuWindowLevel
    try:
        # Above Dock / most chrome
        panel.setLevel_(int(NSPopUpMenuWindowLevel) + 8 + boost)
    except Exception:
        panel.setLevel_(100 + boost)
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())
    panel.setIgnoresMouseEvents_(bool(click_through))
    panel.setHasShadow_(False)
    try:
        panel.setHidesOnDeactivate_(False)
    except Exception:
        pass
    try:
        panel.setCollectionBehavior_(1 << 0 | 1 << 7 | 1 << 3)
    except Exception:
        pass
    if not click_through:
        try:
            panel.setAcceptsMouseMovedEvents_(False)
        except Exception:
            pass


def _cg_to_center_origin(cg_x: float, cg_y: float, size: float) -> tuple[float, float]:
    """Center a size×size panel on the CGEvent hot-spot (cursor tip)."""
    from AppKit import NSScreen
    main = NSScreen.mainScreen()
    if main is None:
        return cg_x - size / 2, -cg_y - size / 2
    mf = main.frame()
    # CG: top-left of primary, y down → Cocoa: bottom-left, y up
    cocoa_cx = float(mf.origin.x) + float(cg_x)
    cocoa_cy = float(mf.origin.y) + float(mf.size.height) - float(cg_y)
    return cocoa_cx - size / 2.0, cocoa_cy - size / 2.0


class _StopChipView:
    """Control chip — only the Stop zone is hittable (status area is click-through)."""
    _cls = None

    @classmethod
    def view_class(cls):
        if cls._cls is not None:
            return cls._cls
        from AppKit import NSView

        class StopChipView(NSView):
            def isFlipped(self):
                return False

            def acceptsFirstMouse_(self, event):
                return True

            def mouseDown_(self, event):
                request_stop("chip")

            def hitTest_(self, point):
                # Only the Stop zone — status/label must not steal clicks
                # meant for the app underneath.
                sf = getattr(self, "stop_frame", None)
                if not sf:
                    # Back-compat if an older layout forgot stop_frame
                    sf = getattr(self, "pill_frame", None)
                if not sf:
                    return None
                x, y, w, h = sf
                try:
                    px, py = float(point.x), float(point.y)
                except Exception:
                    return None
                if x <= px <= x + w and y <= py <= y + h:
                    return self
                return None

        cls._cls = StopChipView
        return cls._cls


class _HaloView:
    """Soft disc under the real system cursor — not a second arrow."""
    _cls = None

    @classmethod
    def view_class(cls):
        if cls._cls is not None:
            return cls._cls
        from AppKit import NSView

        class HaloView(NSView):
            mode = "blue"

            def isFlipped(self):
                return False

            def drawRect_(self, rect):
                from AppKit import NSBezierPath, NSColor, NSRectFill

                NSColor.clearColor().set()
                NSRectFill(self.bounds())

                b = self.bounds()
                cx = b.size.width / 2.0
                cy = b.size.height / 2.0
                # Clear hole so the real cursor tip stays sharp
                outer_r = min(b.size.width, b.size.height) / 2.0 - 0.5
                inner_r = 6.5
                click = self.mode == "red"

                def _ring(r, rr, gg, bb, aa):
                    path = NSBezierPath.bezierPath()
                    path.appendBezierPathWithOvalInRect_(
                        ((cx - r, cy - r), (2 * r, 2 * r))
                    )
                    hole = NSBezierPath.bezierPath()
                    hole.appendBezierPathWithOvalInRect_(
                        ((cx - inner_r, cy - inner_r), (2 * inner_r, 2 * inner_r))
                    )
                    path.appendBezierPath_(hole)
                    try:
                        path.setWindingRule_(1)  # even-odd
                    except Exception:
                        pass
                    NSColor.colorWithCalibratedRed_green_blue_alpha_(
                        rr, gg, bb, aa
                    ).set()
                    path.fill()

                if click:
                    # Amber pulse — confirm the click, then settle
                    _ring(outer_r, 1.00, 0.42, 0.16, 0.22)
                    _ring(outer_r * 0.78, 1.00, 0.52, 0.22, 0.28)
                    _ring(outer_r * 0.56, 1.00, 0.68, 0.34, 0.18)
                    rim_rgb = (1.00, 0.78, 0.42, 0.95)
                    hair_rgb = (1.00, 0.92, 0.76, 0.70)
                else:
                    # Ice ring — readable on light *and* dark, not a second pointer
                    _ring(outer_r, 0.28, 0.58, 1.00, 0.18)
                    _ring(outer_r * 0.80, 0.40, 0.72, 1.00, 0.26)
                    _ring(outer_r * 0.58, 0.62, 0.84, 1.00, 0.16)
                    rim_rgb = (0.82, 0.92, 1.00, 0.95)
                    hair_rgb = (0.95, 0.98, 1.00, 0.55)

                rim = NSBezierPath.bezierPath()
                rim_r = outer_r * 0.86
                rim.appendBezierPathWithOvalInRect_(
                    ((cx - rim_r, cy - rim_r), (2 * rim_r, 2 * rim_r))
                )
                rim.setLineWidth_(1.15)
                NSColor.colorWithCalibratedRed_green_blue_alpha_(*rim_rgb).set()
                rim.stroke()

                hair = NSBezierPath.bezierPath()
                hair.appendBezierPathWithOvalInRect_(
                    ((cx - inner_r - 1.2, cy - inner_r - 1.2),
                     (2 * (inner_r + 1.2), 2 * (inner_r + 1.2)))
                )
                hair.setLineWidth_(0.8)
                NSColor.colorWithCalibratedRed_green_blue_alpha_(*hair_rgb).set()
                hair.stroke()

        cls._cls = HaloView
        return cls._cls


def _make_halo(size: float | None = None):
    global _halo
    from AppKit import NSMakeRect, NSPanel, NSWindowStyleMaskBorderless
    size = size or _SIZE
    _ensure_app()
    if _halo is None:
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, size, size),
            NSWindowStyleMaskBorderless,
            2,
            False,
        )
        _style_panel(panel)
        _halo = panel
    View = _HaloView.view_class()
    view = View.alloc().initWithFrame_(NSMakeRect(0, 0, size, size))
    view.mode = _mode
    _halo.setContentView_(view)
    from AppKit import NSMakeRect as R
    # keep size
    o = _halo.frame().origin
    _halo.setFrame_display_(R(o.x, o.y, size, size), False)
    return _halo


def _place_halo(cg_x: float, cg_y: float, size: float | None = None):
    global _last_cg
    size = size or _SIZE
    if _halo is None:
        _make_halo(size)
    ox, oy = _cg_to_center_origin(cg_x, cg_y, size)
    from AppKit import NSMakeRect
    _halo.setFrame_display_(NSMakeRect(ox, oy, size, size), False)
    _halo.orderFrontRegardless()
    if _banner is not None:
        _banner.orderFrontRegardless()
    _last_cg = (cg_x, cg_y)
    # Window-server frame/order commands only flush when the accessory
    # app's run loop actually spins. This app never calls NSApp.run(), so
    # without a pump here the overlay silently stops updating the instant
    # focus moves to another app (e.g. any click that lands elsewhere) —
    # every high-frequency caller (move/drag) funnels through this
    # function, so pumping here covers all of them from one place.
    # Idle gaps between calls are covered by keep_alive(), not here.
    _pump(n=2, seconds=0.004)


def _make_banner():
    """Build the control session chip: status | Stop.

    Two zones — not one ambiguous "Working · Stop" string. Status is
    click-through; only Stop aborts. Driven-app name when we know it.
    """
    global _banner
    from AppKit import (
        NSColor, NSMakeRect, NSPanel, NSTextField, NSFont, NSView,
        NSWindowStyleMaskBorderless, NSLeftTextAlignment, NSCenterTextAlignment,
    )
    from Quartz import CGColorCreateGenericRGB

    _ensure_app()
    px, py, pw, ph, w, h, pad = _banner_layout()
    # Nonactivating so a Stop click does not steal focus from the driven app.
    style = NSWindowStyleMaskBorderless
    try:
        from AppKit import NSNonactivatingPanelMask
        style = int(NSWindowStyleMaskBorderless) | int(NSNonactivatingPanelMask)
    except Exception:
        pass
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, pw, ph),
        style,
        2,
        False,
    )
    _style_panel(panel, boost=2, click_through=False)
    try:
        panel.setBecomesKeyOnlyIfNeeded_(True)
    except Exception:
        pass

    Root = _StopChipView.view_class()
    root = Root.alloc().initWithFrame_(NSMakeRect(0, 0, pw, ph))
    root.setWantsLayer_(True)
    if root.layer() is not None:
        root.layer().setBackgroundColor_(CGColorCreateGenericRGB(0, 0, 0, 0))

    # Single quiet pill — no bloom stack, no multi-shadow glow.
    pill = NSView.alloc().initWithFrame_(NSMakeRect(pad, pad, w, h))
    pill.setWantsLayer_(True)
    if pill.layer() is not None:
        pill.layer().setCornerRadius_(10.0)
        pill.layer().setBackgroundColor_(
            CGColorCreateGenericRGB(0.07, 0.08, 0.11, 0.92)
        )
        pill.layer().setBorderWidth_(1.0)
        pill.layer().setBorderColor_(
            CGColorCreateGenericRGB(0.50, 0.78, 1.0, 0.55)
        )

    stop_w = 64.0
    status_w = w - stop_w - 1.0
    # Hit target = Stop zone only (right side of the pill).
    root.pill_frame = (pad, pad, w, h)
    root.stop_frame = (pad + status_w, pad, stop_w, h)

    pip = NSView.alloc().initWithFrame_(NSMakeRect(12, (h - 7) / 2.0, 7, 7))
    pip.setWantsLayer_(True)
    if pip.layer() is not None:
        pip.layer().setCornerRadius_(3.5)
        pip.layer().setBackgroundColor_(
            CGColorCreateGenericRGB(0.50, 0.82, 1.0, 1.0)
        )
    pill.addSubview_(pip)
    root._pip = pip

    status = NSTextField.alloc().initWithFrame_(NSMakeRect(26, 7, status_w - 32, h - 14))
    status.setStringValue_(_status_text())
    status.setBezeled_(False)
    status.setDrawsBackground_(False)
    status.setEditable_(False)
    status.setSelectable_(False)
    status.setAlignment_(NSLeftTextAlignment)
    try:
        status.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.92, 0.95))
        status.setFont_(NSFont.systemFontOfSize_weight_(12.0, 0.30))
    except Exception:
        try:
            status.setTextColor_(NSColor.whiteColor())
            status.setFont_(NSFont.systemFontOfSize_(12.0))
        except Exception:
            pass
    pill.addSubview_(status)
    root._status = status

    # Thin divider between status and Stop
    div = NSView.alloc().initWithFrame_(NSMakeRect(status_w, 8, 1.0, h - 16))
    div.setWantsLayer_(True)
    if div.layer() is not None:
        div.layer().setBackgroundColor_(
            CGColorCreateGenericRGB(0.55, 0.80, 1.0, 0.28)
        )
    pill.addSubview_(div)

    stop_lab = NSTextField.alloc().initWithFrame_(
        NSMakeRect(status_w + 2, 7, stop_w - 4, h - 14)
    )
    stop_lab.setStringValue_("Stop")
    stop_lab.setBezeled_(False)
    stop_lab.setDrawsBackground_(False)
    stop_lab.setEditable_(False)
    stop_lab.setSelectable_(False)
    stop_lab.setAlignment_(NSCenterTextAlignment)
    try:
        stop_lab.setTextColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.72, 0.55, 0.98)
        )
        stop_lab.setFont_(NSFont.systemFontOfSize_weight_(12.0, 0.50))
    except Exception:
        try:
            stop_lab.setTextColor_(NSColor.whiteColor())
            stop_lab.setFont_(NSFont.systemFontOfSize_(12.0))
        except Exception:
            pass
    pill.addSubview_(stop_lab)

    root.addSubview_(pill)
    panel.setContentView_(root)
    panel.setFrame_display_(NSMakeRect(px, py, pw, ph), True)
    _banner = panel
    return panel


def _status_text() -> str:
    """Short chip status — driven app when known, else 'Agent'."""
    name = (_driven_label or "").strip()
    if name:
        # Keep the pill readable on a laptop.
        if len(name) > 18:
            name = name[:17] + "…"
        return name
    return "Agent"


def set_driven(label: str | None) -> None:
    """Update the chip's status text (usually the app being driven)."""
    global _driven_label
    _driven_label = (label or "").strip()
    _refresh_chip_labels()


def _refresh_chip_labels() -> None:
    if _banner is None:
        return
    try:
        root = _banner.contentView()
        status = getattr(root, "_status", None) if root is not None else None
        if status is not None:
            status.setStringValue_(_status_text())
        _pulse_pip()
    except Exception:
        pass


def _pulse_pip() -> None:
    """Cheap liveliness cue while a control session is open."""
    global _pip_phase
    if _banner is None:
        return
    try:
        root = _banner.contentView()
        pip = getattr(root, "_pip", None) if root is not None else None
        if pip is None or pip.layer() is None:
            return
        _pip_phase = (_pip_phase + 1) % 6
        # Alternate alpha slightly so idle keep_alive feels alive.
        a = 1.0 if _pip_phase < 3 else 0.45
        from Quartz import CGColorCreateGenericRGB
        pip.layer().setBackgroundColor_(
            CGColorCreateGenericRGB(0.50, 0.82, 1.0, a)
        )
    except Exception:
        pass


def _banner_layout():
    """Chip centered on the window being driven (not the whole display)."""
    from AppKit import NSScreen
    screen = NSScreen.mainScreen()
    pad = 14.0
    # Wider than the old mono-label so status + Stop both read.
    w, h = 220.0, 34.0
    if screen is None:
        return 400.0, 90.0, w + 2 * pad, h + 2 * pad, w, h, pad
    vf = screen.visibleFrame()
    # Prefer the ringed window; sit *outside* it so the pill never
    # covers app pixels (that was a source of accidental clicks).
    if _frame_target is not None:
        gx, gy, gw, gh = _frame_target
        cx, cy, cw, ch = _cg_rect_to_cocoa(gx, gy, gw, gh)
        pill_x = cx + (cw - w) / 2.0
        gap = 10.0
        below = cy - h - gap
        vmin = float(vf.origin.y)
        vmax = vmin + float(vf.size.height) - h
        if below >= vmin:
            pill_y = below
        else:
            above = cy + ch + gap
            pill_y = above if above <= vmax else max(vmin, below)
    else:
        pill_x = float(vf.origin.x) + (float(vf.size.width) - w) / 2.0
        pill_y = float(vf.origin.y) + 18.0
    return (
        pill_x - pad,
        pill_y - pad,
        w + 2 * pad,
        h + 2 * pad,
        w, h, pad,
    )


def keep_alive(seconds: float) -> None:
    """Hold presence visible through an idle wait — call this instead of
    time.sleep() while an action script pauses with presence active.

    Chunks the wait and re-asserts ordering + pumps between chunks, all on
    the calling (main) thread. A background thread sounds like the right
    tool for "keep something alive while I sleep," and an earlier version
    of this file did exactly that — it crashed the whole process every
    time (AppKit hard-aborts on window calls from a non-main thread; no
    Python exception, nothing to catch). This is the safe version: same
    effect, zero threads.

    A Stop click during the wait raises ControlStopped so the script
    cannot continue driving the Mac.
    """
    if _stopped:
        raise ControlStopped(
            "user stopped desktop-harness from the Working chip"
        )
    if not _active:
        time.sleep(max(0.0, seconds))
        if _stopped:
            raise ControlStopped(
                "user stopped desktop-harness from the Working chip"
            )
        return
    remaining = max(0.0, seconds)
    step = 0.08
    while remaining > 0:
        if _stopped:
            raise ControlStopped(
                "user stopped desktop-harness from the Working chip"
            )
        chunk = min(step, remaining)
        time.sleep(chunk)
        remaining -= chunk
        try:
            poll(deep=True)
            if _stopped:
                raise ControlStopped(
                    "user stopped desktop-harness from the Working chip"
                )
            if _halo is not None:
                _halo.orderFrontRegardless()
            if _banner is not None:
                _banner.orderFrontRegardless()
                _pulse_pip()
            if _frame is not None:
                _frame.orderFrontRegardless()
            try:
                from . import stage as _stage
                _stage.tick()
            except Exception:
                pass
        except ControlStopped:
            raise
        except Exception:
            pass


def show(x: float | None = None, y: float | None = None) -> bool:
    global _active, _mode, _session_t0
    if _stopped:
        return False
    if not enabled():
        return False
    try:
        import Quartz
        if x is None or y is None:
            ev = Quartz.CGEventCreate(None)
            p = Quartz.CGEventGetLocation(ev)
            x = float(p.x) if x is None else float(x)
            y = float(p.y) if y is None else float(y)
        else:
            x, y = float(x), float(y)
            Quartz.CGWarpMouseCursorPosition(Quartz.CGPointMake(x, y))
            Quartz.CGAssociateMouseAndMouseCursorPosition(True)

        # ONE cursor: keep system pointer; halo only
        _mode = "blue"
        _make_halo(_SIZE)
        _set_halo_mode("blue")

        global _banner
        if _banner is not None:
            try:
                _banner.orderOut_(None)
            except Exception:
                pass
            _banner = None
        ban = _make_banner()
        ban.orderFrontRegardless()

        _active = True
        if _session_t0 <= 0:
            _session_t0 = time.monotonic()
        _place_halo(x, y, _SIZE)
        try:
            from . import windows as _win
            front = _win.frontmost_app() or {}
            name = front.get("name")
            if name and name.lower() not in ("ghostty", "terminal", "iterm2"):
                set_driven(name)
                ring_window(name)
            else:
                _refresh_chip_labels()
        except Exception:
            _refresh_chip_labels()
        _pump(n=10, seconds=0.03)
        return True
    except Exception as e:
        try:
            print(f"[presence] show failed: {type(e).__name__}: {e}")
        except Exception:
            pass
        return False


def _set_halo_mode(mode: str):
    global _mode
    _mode = mode
    if _halo is None:
        return
    view = _halo.contentView()
    if view is not None and hasattr(view, "mode"):
        view.mode = "red" if mode == "red" else "blue"
        view.setNeedsDisplay_(True)


def move(x: float, y: float) -> None:
    """Warp already done by input.py; place halo on the SAME cg coords — no lag chase."""
    if not enabled():
        return
    if not _active:
        show(x, y)
        return
    try:
        if _halo is None:
            _make_halo(_SIZE)
        if _mode != "blue":
            _set_halo_mode("blue")
        # Same coordinates as CGWarp in the same call stack → synced
        _place_halo(float(x), float(y), _SIZE)
    except Exception:
        pass


def click_flash(x: float, y: float) -> None:
    """Subtle red flash on click, then back to blue — same center, no second cursor."""
    if not enabled():
        return
    try:
        if not _active:
            show(x, y)
        _set_halo_mode("red")
        _place_halo(float(x), float(y), _FLASH)
        _pump(n=4, seconds=0.015)
        time.sleep(0.07)
        _set_halo_mode("blue")
        _place_halo(float(x), float(y), _SIZE)
    except Exception:
        pass


def hide() -> None:
    global _halo, _banner, _frame, _active, _last_cg, _frame_target
    global _driven_label, _session_t0, _pip_phase
    _active = False
    try:
        if _halo is not None:
            _halo.orderOut_(None)
            _halo = None
        if _banner is not None:
            _banner.orderOut_(None)
            _banner = None
        if _frame is not None:
            _frame.orderOut_(None)
            _frame = None
    except Exception:
        pass
    _last_cg = None
    _frame_target = None
    _driven_label = ""
    _session_t0 = 0.0
    _pip_phase = 0
    _pump(n=3, seconds=0.01)


def ensure() -> None:
    """Show presence if enabled and not already up. Cheap no-op when active.

    Mutating helpers call this so AX-only paths (click_text / type / hotkey)
    still surface the Stop chip — without it, the user cannot abort.
    """
    if not enabled():
        return
    if _stopped:
        return
    if _active:
        # Keep labels fresh without rebuilding panels.
        _pulse_pip()
        return
    show()


def active() -> bool:
    """True if the halo/banner are currently shown.

    Lets a caller outside this module (the daemon's idle loop) check state
    without reaching into the private `_active` global directly.
    """
    return _active


def chip_frame() -> dict[str, float] | None:
    """CG bounds of the Working · Stop chip, or None if it is hidden."""
    if _banner is None:
        return None
    try:
        from AppKit import NSScreen
        f = _banner.frame()
        main = NSScreen.mainScreen()
        if main is None:
            return None
        mf = main.frame()
        # Cocoa bottom-left → CG top-left
        x = float(f.origin.x) - float(mf.origin.x)
        y = float(mf.origin.y) + float(mf.size.height) - (
            float(f.origin.y) + float(f.size.height)
        )
        return {
            "x": x,
            "y": y,
            "w": float(f.size.width),
            "h": float(f.size.height),
        }
    except Exception:
        return None


def pulse():
    import Quartz
    ev = Quartz.CGEventCreate(None)
    p = Quartz.CGEventGetLocation(ev)
    click_flash(float(p.x), float(p.y))


def _cg_rect_to_cocoa(x: float, y: float, w: float, h: float):
    """CG top-left → Cocoa bottom-left for the main screen."""
    from AppKit import NSScreen
    main = NSScreen.mainScreen()
    if main is None:
        return x, -y - h, w, h
    mf = main.frame()
    cocoa_x = float(mf.origin.x) + float(x)
    cocoa_y = float(mf.origin.y) + float(mf.size.height) - float(y) - float(h)
    return cocoa_x, cocoa_y, float(w), float(h)


class _FrameView:
    """Hollow ice rectangle — Google-style agent chrome, Grok color."""
    _cls = None

    @classmethod
    def view_class(cls):
        if cls._cls is not None:
            return cls._cls
        from AppKit import NSView

        class FrameView(NSView):
            def isFlipped(self):
                return False

            def drawRect_(self, rect):
                from AppKit import NSBezierPath, NSColor, NSRectFill
                NSColor.clearColor().set()
                NSRectFill(self.bounds())
                b = self.bounds()
                # Sequoia window chrome is ~14pt. Stroke is centered on
                # the glass edge (panel padded by half the line width).
                stroke = 2.5
                half = stroke / 2.0
                radius = 20.0
                path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    ((half, half), (b.size.width - stroke, b.size.height - stroke)),
                    radius,
                    radius,
                )
                path.setLineWidth_(stroke)
                NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    _ICE[0], _ICE[1], _ICE[2], 0.94
                ).set()
                path.stroke()

        cls._cls = FrameView
        return cls._cls


def ring_window(app: str | int | None = None, window_id: int | None = None) -> bool:
    """Draw a click-through ice frame around the window the agent is driving.

    Only while presence is active. No second picture of the window.
    """
    global _frame, _frame_target
    if not enabled():
        return False
    if not _active:
        show()
        if not _active:
            return False
    try:
        from . import windows as _win
        if window_id is not None:
            fr = None
            for w in _win.list_windows():
                if w.get("id") == int(window_id):
                    fr = w
                    break
            if fr is None:
                return False
        else:
            fr = _win.window_frame(app)
        x, y, w, h = float(fr["x"]), float(fr["y"]), float(fr["w"]), float(fr["h"])
        # Half-stroke pad so the line is centered on the window edge.
        pad = 1.25
        x, y, w, h = x - pad, y - pad, w + 2 * pad, h + 2 * pad
        _frame_target = (x, y, w, h)
        # Prefer a human-readable owner name on the chip.
        owner = (fr.get("app") or "").strip()
        if owner:
            set_driven(owner)
        elif isinstance(app, str) and app.strip():
            set_driven(app.strip())
        cx, cy, cw, ch = _cg_rect_to_cocoa(x, y, w, h)
        _ensure_app()
        from AppKit import NSMakeRect, NSPanel, NSWindowStyleMaskBorderless
        if _frame is None:
            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(cx, cy, cw, ch),
                NSWindowStyleMaskBorderless,
                2,
                False,
            )
            _style_panel(panel, boost=1)
            View = _FrameView.view_class()
            view = View.alloc().initWithFrame_(NSMakeRect(0, 0, cw, ch))
            panel.setContentView_(view)
            _frame = panel
        else:
            _frame.setFrame_display_(NSMakeRect(cx, cy, cw, ch), False)
            try:
                _frame.contentView().setFrame_(NSMakeRect(0, 0, cw, ch))
                _frame.contentView().setNeedsDisplay_(True)
            except Exception:
                pass
        _frame.orderFrontRegardless()
        _place_banner()
        _pump(n=2, seconds=0.006)
        return True
    except Exception:
        return False


def _place_banner() -> None:
    """Re-center the Working chip on the ringed window."""
    if _banner is None:
        return
    try:
        px, py, pw, ph, _, _, _ = _banner_layout()
        from AppKit import NSMakeRect
        _banner.setFrame_display_(NSMakeRect(px, py, pw, ph), False)
        _banner.orderFrontRegardless()
    except Exception:
        pass


# --- wire input.py overlay API ---
def set_overlay(_):
    pass
