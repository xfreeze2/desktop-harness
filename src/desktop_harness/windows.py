"""Window and app discovery via CGWindowList + NSWorkspace."""
from __future__ import annotations

import time
from typing import Any

import Quartz
from AppKit import NSRunningApplication, NSWorkspace
from CoreFoundation import CFRunLoopRunInMode, kCFRunLoopDefaultMode


def _refresh_workspace() -> None:
    """Deliver pending NSWorkspace notifications before reading its caches.

    `runningApplications()` and `frontmostApplication()` are caches that only
    update when the host process pumps a run loop. Neither the CLI nor the warm
    daemon ever does, so both stay frozen at process start: apps launched later
    are invisible (so `activate()` times out on every cold launch) and apps that
    have quit linger indefinitely. A zero timeout drains what is already pending
    without blocking.
    """
    CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.0, True)


def list_apps() -> list[dict[str, Any]]:
    """Running apps with a regular activation policy (skip agents/UI helpers)."""
    _refresh_workspace()
    out = []
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        # 0 = regular, 1 = accessory, 2 = prohibited
        if app.activationPolicy() != 0:
            continue
        out.append({
            "name": app.localizedName() or "",
            "bundle_id": app.bundleIdentifier() or "",
            "pid": int(app.processIdentifier()),
            "active": bool(app.isActive()),
            "hidden": bool(app.isHidden()),
        })
    out.sort(key=lambda a: (not a["active"], a["name"].lower()))
    return out


# CGWindowList is the expensive part of window_frame / screenshot / ring.
# A single agent step can call it several times in a few milliseconds
# against a desktop that has not moved. 80ms never hides a real window
# change (activate/settle waits are longer) but collapses the repeats.
_WIN_CACHE_TTL = 0.08
_win_cache: tuple[float, bool, list[dict[str, Any]]] | None = None


def _invalidate_window_cache() -> None:
    global _win_cache
    _win_cache = None


def list_windows(on_screen_only: bool = True) -> list[dict[str, Any]]:
    """On-screen windows with bounds (global screen points)."""
    global _win_cache
    now = time.monotonic()
    if (
        _win_cache is not None
        and _win_cache[1] is on_screen_only
        and (now - _win_cache[0]) < _WIN_CACHE_TTL
    ):
        return list(_win_cache[2])
    opts = Quartz.kCGWindowListOptionOnScreenOnly if on_screen_only else 0
    raw = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    out = []
    for w in raw:
        layer = w.get("kCGWindowLayer", 0)
        if layer != 0:
            continue
        b = w.get("kCGWindowBounds") or {}
        width = float(b.get("Width", 0))
        height = float(b.get("Height", 0))
        if width < 50 or height < 50:
            continue
        out.append({
            "id": int(w.get("kCGWindowNumber", 0)),
            "app": w.get("kCGWindowOwnerName") or "",
            "pid": int(w.get("kCGWindowOwnerPID", 0)),
            "title": w.get("kCGWindowName") or "",
            "x": float(b.get("X", 0)),
            "y": float(b.get("Y", 0)),
            "w": width,
            "h": height,
        })
    _win_cache = (time.monotonic(), on_screen_only, out)
    return list(out)


def window_frame(app: str | int | None = None) -> dict[str, Any]:
    """Largest on-screen window for an app, in **global** screen points.

    Prefer this when mapping screenshot pixels → clicks: window-local
    ``(px, py)`` becomes global ``(frame["x"] + px, frame["y"] + py)``.
    ``app=None`` → frontmost app. Raises if no matching window.
    """
    if app is None:
        front = frontmost_app()
        if not front:
            raise RuntimeError("no frontmost app for window_frame")
        name = front.get("name") or ""
        pid = front.get("pid")
    elif isinstance(app, int):
        info = find_app(app)
        name = (info or {}).get("name") or ""
        pid = app
    else:
        name = str(app)
        info = find_app(app)
        pid = (info or {}).get("pid")

    def _match(wins: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        q = (name or "").lower()
        for w in wins:
            owner = (w.get("app") or "").lower()
            # Owner / pid only — never match because some *other* app's title
            # mentions us (a Ghostty tab named "Notes" is not Notes.app).
            if pid is not None and int(w.get("pid") or 0) == int(pid):
                if float(w.get("w") or 0) >= 50 and float(w.get("h") or 0) >= 50:
                    out.append(w)
                continue
            if q and (owner == q or q in owner):
                if float(w.get("w") or 0) >= 50 and float(w.get("h") or 0) >= 50:
                    out.append(w)
        return out

    wins = list_windows(on_screen_only=True)
    matched = _match(wins)
    # Frontmost but on another Space / "off-screen" to CGWindowList —
    # still a real window we can capture and drive after activate.
    if not matched:
        matched = _match(list_windows(on_screen_only=False))
    if not matched and app is None and wins:
        front = frontmost_app() or {}
        fname = (front.get("name") or "").lower()
        fpid = front.get("pid")
        matched = [
            w for w in wins
            if (fpid and int(w.get("pid") or 0) == int(fpid))
            or (fname and fname in (w.get("app") or "").lower())
        ]
        if not matched:
            matched = list(wins)
    if not matched:
        raise RuntimeError(
            f"no on-screen window for app {app!r} "
            f"(name={name!r} pid={pid!r}; {len(wins)} windows visible)"
        )
    # Largest by area — main content, not a tiny utility panel
    best = max(matched, key=lambda w: float(w.get("w", 0)) * float(w.get("h", 0)))
    return {
        "id": best.get("id"),
        "app": best.get("app"),
        "pid": best.get("pid"),
        "title": best.get("title"),
        "x": float(best["x"]),
        "y": float(best["y"]),
        "w": float(best["w"]),
        "h": float(best["h"]),
    }


def win_to_global(
    x: float,
    y: float,
    app: str | int | None = None,
    *,
    frame: dict[str, Any] | None = None,
) -> tuple[float, float]:
    """Map window-local (screenshot) coords → global screen points."""
    fr = frame if frame is not None else window_frame(app)
    return float(fr["x"]) + float(x), float(fr["y"]) + float(y)


def frontmost_app() -> dict[str, Any] | None:
    _refresh_workspace()
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if not app:
        return None
    return {
        "name": app.localizedName() or "",
        "bundle_id": app.bundleIdentifier() or "",
        "pid": int(app.processIdentifier()),
        "active": True,
        "hidden": bool(app.isHidden()),
    }


def find_app(name_or_bundle: str | int) -> dict[str, Any] | None:
    """Match by localized name, bundle id, or pid.

    Resolution order:
      1. exact name or exact bundle id
      2. name startswith query
      3. best substring (shortest name wins — avoids "Text" → wrong app)
      4. bundle id via NSRunningApplication
    """
    # pid path
    if isinstance(name_or_bundle, int):
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
            name_or_bundle)
        if not app:
            return None
        return {
            "name": app.localizedName() or "",
            "bundle_id": app.bundleIdentifier() or "",
            "pid": int(app.processIdentifier()),
            "active": bool(app.isActive()),
            "hidden": bool(app.isHidden()),
        }

    q = (name_or_bundle or "").strip().lower()
    if not q:
        return None

    apps = list_apps()
    # 1) exact
    for a in apps:
        if a["name"].lower() == q or a["bundle_id"].lower() == q:
            return a
    # 2) startswith name
    starts = [a for a in apps if a["name"].lower().startswith(q)]
    if len(starts) == 1:
        return starts[0]
    if len(starts) > 1:
        starts.sort(key=lambda a: len(a["name"]))
        return starts[0]
    # 3) substring — prefer shortest name containing q (most specific)
    # Refuse very short queries: "a" / "te" match almost everything and
    # used to return the first alphabetical hit (wrong app, wrong clicks).
    if len(q) < 3:
        return None
    subs = [a for a in apps if q in a["name"].lower() or q in a["bundle_id"].lower()]
    if subs:
        subs.sort(key=lambda a: (len(a["name"]), a["name"].lower()))
        return subs[0]
    # 4) bundle id launch lookup
    ns_apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(
        name_or_bundle)
    if ns_apps:
        app = ns_apps[0]
        return {
            "name": app.localizedName() or "",
            "bundle_id": app.bundleIdentifier() or "",
            "pid": int(app.processIdentifier()),
            "active": bool(app.isActive()),
            "hidden": bool(app.isHidden()),
        }
    return None


def activate(name_or_bundle: str, wait: float | None = None) -> dict[str, Any]:
    """Bring app to front. Launches via `open -a` / NSWorkspace if needed.

    wait: seconds after activate. Default 0.12 if already running, 0.35 if cold launch.
    """
    import subprocess
    from . import safety as _safety

    _safety.check_app_allowed(name_or_bundle)
    app_info = find_app(name_or_bundle)
    cold = app_info is None
    if app_info is None:
        # `open -a` resolves system apps more reliably than launchApplication_
        r = subprocess.run(
            ["open", "-a", name_or_bundle],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            ok = NSWorkspace.sharedWorkspace().launchApplication_(name_or_bundle)
            if not ok:
                err = (r.stderr or r.stdout or "").strip()
                raise RuntimeError(
                    f"app not found / could not launch: {name_or_bundle!r} ({err})")
        # poll until it appears in the running list (tighter than before)
        deadline = time.time() + 4.0
        while time.time() < deadline:
            time.sleep(0.08)
            app_info = find_app(name_or_bundle)
            if app_info:
                break
        if app_info is None:
            raise RuntimeError(f"launched but could not resolve app: {name_or_bundle!r}")
    # already frontmost → skip activate + sleep
    if app_info.get("active") and not cold:
        _safety.audit("activate_skip", {"name": name_or_bundle, "reason": "already_frontmost"})
        return app_info
    _invalidate_window_cache()
    apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(
        app_info["bundle_id"]) if app_info["bundle_id"] else []
    if apps:
        apps[0].activateWithOptions_(1 << 1)  # ignoring other apps
    else:
        # fallback: activate by PID
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
            app_info["pid"])
        if app:
            app.activateWithOptions_(1 << 1)
    # Confirm activation by polling the real signal (frontmost app switched)
    # instead of blind-sleeping the whole budget first. activateWithOptions_
    # is async and often lands in a few ms; a flat pre-sleep paid the full
    # 120-350ms on every call regardless. Poll immediately, cap the total
    # wait at the old budget so behavior on a slow/contested activation
    # (another app stealing focus) is unchanged.
    budget = (0.35 if cold else 0.12) if wait is None else wait
    deadline = time.time() + max(budget, 1.2)
    poll = 0.02
    while time.time() < deadline:
        cur = find_app(name_or_bundle)
        if cur and cur.get("active"):
            _safety.audit("activate", {"name": name_or_bundle, "cold": cold})
            return cur
        if apps:
            apps[0].activateWithOptions_(1 << 1)
        time.sleep(poll)
    _safety.audit("activate", {"name": name_or_bundle, "cold": cold, "warn": "focus_uncertain"})
    return find_app(name_or_bundle) or app_info


def open_app(name: str) -> dict[str, Any]:
    """Alias for activate — open or focus an app by name."""
    return activate(name)
