"""Accessibility-tree perception and element actions — the primary eyes/hands path."""
from __future__ import annotations

import time
from typing import Any

from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXUIElementCreateSystemWide,
    AXUIElementPerformAction,
    AXUIElementSetAttributeValue,
    AXValueGetType,
    AXValueGetValue,
    kAXChildrenAttribute,
    kAXDescriptionAttribute,
    kAXEnabledAttribute,
    kAXErrorSuccess,
    kAXFocusedUIElementAttribute,
    kAXPositionAttribute,
    kAXPressAction,
    kAXRoleAttribute,
    kAXRoleDescriptionAttribute,
    kAXSizeAttribute,
    kAXTitleAttribute,
    kAXValueAttribute,
    kAXWindowsAttribute,
)
from . import windows as winmod

# Roles that are usually worth keeping in a compact snapshot.
_INTERACTIVE = {
    "AXButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXMenuButton",
    "AXTextField", "AXTextArea", "AXSearchField", "AXComboBox", "AXLink",
    "AXMenuItem", "AXMenuBarItem", "AXTab", "AXSlider", "AXIncrementor",
    "AXDisclosureTriangle", "AXRow", "AXCell", "AXStaticText", "AXImage",
    "AXToolbar", "AXList", "AXOutline", "AXTable", "AXScrollArea",
    "AXWindow", "AXSheet", "AXDialog", "AXGroup", "AXSplitGroup",
}


def _copy(el, attr) -> Any:
    err, val = AXUIElementCopyAttributeValue(el, attr, None)
    if err != kAXErrorSuccess:
        return None
    return val


def _unpack_ax_value(val) -> dict[str, float] | None:
    """Decode AXValue (CGPoint or CGSize) robustly across pyobjc builds."""
    if val is None:
        return None
    try:
        t = AXValueGetType(val)
    except Exception:
        t = None
    # Preferred: pass a real CGPoint/CGSize buffer
    try:
        import Quartz
        if t == 1:  # kAXValueCGPointType
            pt = Quartz.CGPoint()
            ok = AXValueGetValue(val, t, pt)
            if ok or hasattr(pt, "x"):
                return {"x": float(pt.x), "y": float(pt.y)}
        if t == 2:  # kAXValueCGSizeType
            sz = Quartz.CGSize()
            ok = AXValueGetValue(val, t, sz)
            if ok or hasattr(sz, "width"):
                return {"w": float(sz.width), "h": float(sz.height)}
    except Exception:
        pass
    try:
        if t is not None:
            ok, decoded = AXValueGetValue(val, t, None)
            if decoded is not None:
                if hasattr(decoded, "x") and hasattr(decoded, "y"):
                    return {"x": float(decoded.x), "y": float(decoded.y)}
                if hasattr(decoded, "width") and hasattr(decoded, "height"):
                    return {"w": float(decoded.width), "h": float(decoded.height)}
                if isinstance(decoded, (tuple, list)) and len(decoded) >= 2:
                    a, b = float(decoded[0]), float(decoded[1])
                    return {"x": a, "y": b} if t == 1 else {"w": a, "h": b}
    except Exception:
        pass
    try:
        if hasattr(val, "x") and hasattr(val, "y"):
            return {"x": float(val.x), "y": float(val.y)}
        if hasattr(val, "width") and hasattr(val, "height"):
            return {"w": float(val.width), "h": float(val.height)}
    except Exception:
        pass
    return None


def _frame(el) -> dict[str, float] | None:
    pos = _unpack_ax_value(_copy(el, kAXPositionAttribute))
    size = _unpack_ax_value(_copy(el, kAXSizeAttribute))
    if not pos or "x" not in pos:
        return None
    if not size or "w" not in size:
        return None
    return {"x": float(pos["x"]), "y": float(pos["y"]),
            "w": float(size["w"]), "h": float(size["h"])}


def frame_on_screen(frame: dict | None) -> bool:
    """True if frame center looks like a real on-screen control (not a phantom)."""
    if not frame:
        return False
    try:
        import Quartz
        bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        # multi-monitor: allow generous bounds around main + secondary via union of on-screen windows
        max_x = float(bounds.size.width) + float(bounds.origin.x) + 4000
        max_y = float(bounds.size.height) + float(bounds.origin.y) + 4000
        min_x = float(bounds.origin.x) - 2000
        min_y = float(bounds.origin.y) - 200
    except Exception:
        min_x, min_y, max_x, max_y = -2000, -200, 8000, 5000
    cx = frame["x"] + frame.get("w", 0) / 2
    cy = frame["y"] + frame.get("h", 0) / 2
    if frame.get("w", 0) <= 0 or frame.get("h", 0) <= 0:
        return False
    # reject absurd sizes (full virtual desktop glitches)
    if frame.get("w", 0) > 4000 or frame.get("h", 0) > 3000:
        return False
    return min_x <= cx <= max_x and min_y <= cy <= max_y


def _str_attr(el, attr) -> str:
    v = _copy(el, attr)
    if v is None:
        return ""
    return str(v).strip()


def _children(el, *, prioritize_windows: bool = False) -> list:
    kids = _copy(el, kAXChildrenAttribute)
    if kids is None:
        return []
    try:
        kids = list(kids)
    except TypeError:
        return []
    if prioritize_windows and len(kids) > 1:
        # Real UI (buttons, transport controls, fields) lives in windows;
        # AXMenuBar's first item is the shared system Apple menu, and a
        # busy app's own menus (Recent Items, track/subtitle lists, …)
        # can be hundreds of nodes. Walked depth-first in raw AXChildren
        # order (menu bar first, as macOS returns it), that alone can
        # exhaust max_nodes before a single window is ever visited —
        # measured on VLC: 400-node budget, 379 AXMenuItems, 0 windows
        # reached. Windows first means the interactive-only fast pass in
        # find() actually sees real controls instead of always falling
        # through to the expensive full-tree rescan.
        def _rank(c) -> int:
            role = _str_attr(c, kAXRoleAttribute)
            if role == "AXWindow":
                return 0
            if role == "AXMenuBar":
                return 2
            return 1
        kids = sorted(kids, key=_rank)
    return kids


def app_element(name_or_pid: str | int | None = None):
    """AXUIElement for an app. None → frontmost."""
    if name_or_pid is None:
        front = winmod.frontmost_app()
        if not front:
            raise RuntimeError("no frontmost app")
        pid = front["pid"]
    elif isinstance(name_or_pid, int):
        pid = name_or_pid
    else:
        info = winmod.find_app(name_or_pid)
        if not info:
            raise RuntimeError(f"app not found: {name_or_pid!r}")
        pid = info["pid"]
    return AXUIElementCreateApplication(pid), pid


def _node_dict(el, path: str, depth: int) -> dict[str, Any]:
    role = _str_attr(el, kAXRoleAttribute)
    title = _str_attr(el, kAXTitleAttribute)
    value = _str_attr(el, kAXValueAttribute)
    desc = _str_attr(el, kAXDescriptionAttribute)
    role_desc = _str_attr(el, kAXRoleDescriptionAttribute)
    enabled = _copy(el, kAXEnabledAttribute)
    frame = _frame(el)
    label = title or desc or (value[:80] if value else "") or role_desc
    return {
        "role": role,
        "title": title,
        "value": value[:200] if value else "",
        "description": desc,
        "label": label,
        "enabled": bool(enabled) if enabled is not None else True,
        "frame": frame,
        "path": path,
        "depth": depth,
        "_el": el,  # internal; stripped before print
    }


def walk(
    el,
    *,
    max_depth: int = 12,
    max_nodes: int = 400,
    interactive_only: bool = False,
    include_menubar: bool = False,
    path: str = "0",
    depth: int = 0,
    out: list | None = None,
) -> list[dict[str, Any]]:
    """Depth-first collect of nodes.

    ``include_menubar=False`` (default) skips descending into AXMenuBar.
    Menu bars often hold hundreds of system items (Writing Tools, Recent
    Items, …) that burn the whole ``max_nodes`` budget before any window
    content is seen — especially Canva/Electron. Pass ``include_menubar=True``
    when you actually need menu items (File → Save, app menus).
    """
    if out is None:
        out = []
    if depth > max_depth or len(out) >= max_nodes:
        return out
    role = _str_attr(el, kAXRoleAttribute)
    # Skip menubar subtrees entirely unless explicitly requested
    if role == "AXMenuBar" and not include_menubar:
        return out
    node = _node_dict(el, path, depth)
    keep = True
    if interactive_only and role and role not in _INTERACTIVE:
        # still descend into containers
        keep = role in {
            "AXWindow", "AXGroup", "AXSplitGroup", "AXScrollArea",
            "AXList", "AXOutline", "AXTable", "AXToolbar", "AXTabGroup",
            "AXMenuBar", "AXMenu", "AXSheet", "AXDialog", "AXLayoutArea",
            "AXSplitGroup", "AXBrowser", "AXGenericElement",
        }
        if not keep and not (node["title"] or node["value"] or node["description"]):
            # skip pure noise leaf
            pass
        else:
            keep = True if (node["title"] or node["description"] or node["value"]
                            or role in _INTERACTIVE) else (depth < 3)
    if keep:
        # Prefer nodes with a label or interactive role
        if (node["label"] or role in _INTERACTIVE or depth <= 1):
            out.append(node)
    kids = _children(el, prioritize_windows=(role == "AXApplication"))
    for i, child in enumerate(kids):
        if len(out) >= max_nodes:
            break
        walk(
            child,
            max_depth=max_depth,
            max_nodes=max_nodes,
            interactive_only=interactive_only,
            include_menubar=include_menubar,
            path=f"{path}.{i}",
            depth=depth + 1,
            out=out,
        )
    return out


# Short-lived cache of raw walk() output, keyed by what actually changes
# the result: which app, and how the walk was shaped. A single agent step
# (e.g. ensure_media_playing, or find() falling through to a rescan) can
# trigger several full-tree walks within milliseconds of each other against
# an app whose UI hasn't moved; walking the live AX tree is the genuinely
# slow part (tens of ms of cross-process calls), not the tiny dict-copy
# below. 150ms is short enough that it never masks a real UI change (every
# helper's own settle waits are >= that) but long enough to collapse the
# back-to-back re-queries that were costing 3-4 walks for one action.
_WALK_CACHE_TTL = 0.15
_walk_cache: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}


def _cached_walk(
    root,
    pid,
    *,
    max_depth: int,
    max_nodes: int,
    interactive_only: bool,
    include_menubar: bool = False,
) -> list[dict[str, Any]]:
    key = (pid, max_depth, max_nodes, interactive_only, include_menubar)
    now = time.monotonic()
    hit = _walk_cache.get(key)
    if hit is not None and (now - hit[0]) < _WALK_CACHE_TTL:
        return hit[1]
    nodes = walk(
        root,
        max_depth=max_depth,
        max_nodes=max_nodes,
        interactive_only=interactive_only,
        include_menubar=include_menubar,
    )
    # Stamp with the time the walk *finished*, not started — the walk
    # itself can take 100-300ms on a busy app, and a start-time stamp
    # would burn most of the TTL before the entry is even usable.
    _walk_cache[key] = (time.monotonic(), nodes)
    return nodes


def ax_snapshot(
    app: str | int | None = None,
    *,
    max_depth: int = 10,
    max_nodes: int = 300,
    interactive_only: bool = True,
    include_el: bool = False,
    include_menubar: bool = False,
) -> list[dict[str, Any]]:
    """Compact AX node list for the app (default: frontmost).

    Menubar is skipped by default so the node budget goes to real window
    content. Pass ``include_menubar=True`` when targeting menu items.
    """
    root, pid = app_element(app)
    cached = _cached_walk(
        root, pid,
        max_depth=max_depth, max_nodes=max_nodes, interactive_only=interactive_only,
        include_menubar=include_menubar,
    )
    # Copy each node dict — callers below (and ax_snapshot's own callers)
    # mutate/strip keys (e.g. popping "_el"); the cache must stay pristine
    # or a later include_el=True caller would silently get stripped nodes.
    nodes = [dict(n) for n in cached]
    # Also pull windows explicitly so titles show up early
    wins = _copy(root, kAXWindowsAttribute) or []
    try:
        wins = list(wins)
    except TypeError:
        wins = []
    for i, w in enumerate(wins[:8]):
        title = _str_attr(w, kAXTitleAttribute)
        if title:
            # ensure window title present
            if not any(n.get("title") == title and n.get("role") == "AXWindow" for n in nodes):
                nodes.insert(0, {
                    "role": "AXWindow",
                    "title": title,
                    "value": "",
                    "description": "",
                    "label": title,
                    "enabled": True,
                    "frame": _frame(w),
                    "path": f"win.{i}",
                    "depth": 0,
                    "_el": w,
                })
    if not include_el:
        for n in nodes:
            n.pop("_el", None)
    return nodes


def find(
    text: str,
    app: str | int | None = None,
    *,
    role: str | None = None,
    max_results: int = 10,
    include_el: bool = False,
) -> list[dict[str, Any]]:
    """Find nodes whose title/value/description contains text (case-insensitive).

    Uses a smaller interactive-first pass, then expands only if needed.

    By default strips the internal ``_el`` (AXUIElementRef) so results are
    JSON-serializable — same contract as ``ax_snapshot``. Pass
    ``include_el=True`` only when a local press/set-value path needs the ref.
    """
    q = text.strip().lower()
    if not q:
        return []

    def score_node(n: dict) -> int | None:
        if role and n.get("role") != role and not (n.get("role") or "").endswith(role):
            return None
        title = (n.get("title") or "").lower()
        label = (n.get("label") or "").lower()
        desc = (n.get("description") or "").lower()
        value = (n.get("value") or "").lower()
        blob = f"{title} {label} {desc} {value}"
        if q not in blob:
            return None
        # Prefer exact / whole-token matches so "Play" does not beat
        # "Play all" / "Playing from" by accident when both contain "play".
        score = 20
        if title == q or label == q:
            score = 120
        elif title.startswith(q + " ") or label.startswith(q + " "):
            score = 90
        elif title.startswith(q) or label.startswith(q):
            # "Play…" longer labels still score high but below exact
            score = 75
        elif f" {q} " in f" {title} " or f" {q} " in f" {label} ":
            score = 70
        elif q in title or q in label:
            score = 45
        else:
            score = 25  # only in desc/value
        # Penalize clearly different multi-word labels when query is a short word
        primary = label or title
        if " " not in q and primary and " " in primary and primary != q and not primary.startswith(q + " "):
            # e.g. query "play" vs label "playing from" / "play all"
            if not primary.startswith(q):
                score -= 25
            elif primary.split()[0] != q:
                score -= 15
            else:
                # starts with query but has more words ("play all") — still below exact
                score = min(score, 70)
        if n.get("role") in ("AXButton", "AXLink", "AXCheckBox", "AXMenuItem",
                             "AXRadioButton", "AXPopUpButton"):
            score += 15
        elif n.get("role") in _INTERACTIVE:
            score += 5
        # Transport words (Play/Pause/Next/Previous) appear many times in
        # list rows. Prefer the lowest on-screen hit — that's the player bar.
        if q in ("play", "pause", "next", "previous", "prev") and (
            title == q or label == q
        ):
            fr = n.get("frame") or {}
            y = float(fr.get("y") or 0)
            h = float(fr.get("h") or 0)
            if y > 700:
                score += 40
            elif y > 400:
                score += 10
            # Tiny 16–24px chrome buttons in a queue are worse than the bar
            if 20 <= h <= 48 and y > 600:
                score += 15
        return score

    # Fast path: interactive-only compact tree (windows only — skip menubar noise)
    nodes = ax_snapshot(
        app, max_nodes=220, max_depth=9, interactive_only=True,
        include_el=True, include_menubar=False,
    )
    hits: list[tuple[int, dict]] = []
    for n in nodes:
        s = score_node(n)
        if s is not None:
            hits.append((s, n))
            if s >= 100 and len(hits) >= 1:
                # exact title/label — good enough, skip deep rescan
                break
    # Slow path only if nothing useful. Use the *best* score, not the
    # first node in tree order — a weak desc-match listed before an
    # exact button used to force a full menubar walk every time.
    best = max((s for s, _ in hits), default=0)
    if best < 60:
        nodes = ax_snapshot(
            app, max_nodes=450, max_depth=12, interactive_only=False,
            include_el=True, include_menubar=True,
        )
        hits = []
        for n in nodes:
            s = score_node(n)
            if s is not None:
                hits.append((s, n))

    # Prefer on-screen frames (multi-monitor AX ghosts are common)
    ranked: list[tuple[int, dict]] = []
    for score, n in hits:
        fr = n.get("frame")
        if fr and not frame_on_screen(fr):
            score -= 40
        ranked.append((score, n))
    ranked.sort(key=lambda x: -x[0])
    out = []
    for score, n in ranked[:max_results]:
        item = {k: v for k, v in n.items() if k != "_el"}
        item["score"] = score
        if include_el:
            item["_el"] = n.get("_el")
        out.append(item)
    return out


def _invalidate_walk_cache() -> None:
    """Drop cached AX walks after a mutation so the next read is live."""
    _walk_cache.clear()


def press_element(el) -> bool:
    err = AXUIElementPerformAction(el, kAXPressAction)
    if err == kAXErrorSuccess:
        _invalidate_walk_cache()
    return err == kAXErrorSuccess


def set_value(el, value: str) -> bool:
    err = AXUIElementSetAttributeValue(el, kAXValueAttribute, value)
    if err == kAXErrorSuccess:
        _invalidate_walk_cache()
    return err == kAXErrorSuccess


def focused_element() -> dict[str, Any] | None:
    sys = AXUIElementCreateSystemWide()
    el = _copy(sys, kAXFocusedUIElementAttribute)
    if el is None:
        return None
    n = _node_dict(el, "focused", 0)
    n.pop("_el", None)
    return n


def public_nodes(nodes: list[dict]) -> list[dict]:
    """Strip internal keys for printing."""
    out = []
    for n in nodes:
        out.append({k: v for k, v in n.items() if not k.startswith("_")})
    return out
