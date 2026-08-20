# How desktop-harness works (plain English)

## What is this product?

**Name:** `desktop-harness`  
**One line:** A small program on your Mac that **Grok Build** (and other coding agents) call to open apps, read the UI, move the mouse, click, and type.

**Built for Grok Build.** Works with anything that can run shell commands.

**It is not an MCP server.** It’s a **CLI** plus an **agent skill** file. The agent runs:

```bash
desktop-harness <<'PY'
open_app("Safari")
print(labels()[:10])
PY
```

Optional **daemon** keeps the program warm so the *second* action is much faster than restarting Python every time.

When the **next frame** is the action, a chat turn is too slow. Use
`grab_frame` + `find_color` / `scan_column` + `run_loop` so see→act
stays in one process. The script names the colors and keys. The harness
does not know what app it is looking at.

---

## Can it move the real mouse?

**Yes.** The harness moves the **real system cursor**, clicks, drags, scrolls, and types. You can watch the pointer on your screen.

---

## The two “eyes” and the “hands”

```
┌─────────────────────────────────────────────────────────┐
│  AGENT (Grok Build primary; others via shell)           │
│    runs:  desktop-harness <<'PY' ...                     │
└───────────────────────┬─────────────────────────────────┘
                        │
          ┌─────────────▼─────────────┐
          │      helpers.py           │
          └─────────────┬─────────────┘
       ┌────────────────┼────────────────┐
       ▼                ▼                ▼
  AX tree           Screenshot        CGEvent
  (fast eyes)       (pixel eyes)      (hands)
  ax.py             capture.py        input.py
```

| Piece | What it is |
|-------|------------|
| **AX tree** | macOS Accessibility: buttons, labels, fields as structured text — **primary** |
| **Screenshot** | Picture of a window if AX is empty — **fallback** |
| **CGEvent + warp** | Move **your real mouse**, click, type |
| **Agent cursor circle** | Optional colored ring so you *see* agent intent |

---

## Mouse control — what actually happens

When the agent runs `move_to(500, 300)` or `click(500, 300)`:

1. **`CGWarpMouseCursorPosition`** — moves the **visible** macOS pointer  
2. **`CGEventPost` (mouse moved / down / up)** — apps receive a real click  
3. Optional **overlay circle** tracks the same point  

This is the same HID path assistive tools and automation frameworks use. **Accessibility** permission is required.

### What you can do today

| Call | Effect |
|------|--------|
| `mouse_pos()` | Where is the pointer now? |
| `move_to(x, y)` | Animate pointer there |
| `move_by(dx, dy)` | Nudge |
| `wiggle()` | Small shake = “thinking” |
| `click(x, y)` | Move + left click |
| `right_click(x, y)` | Context menu |
| `drag(x1,y1,x2,y2)` | Click-drag |
| `scroll(dy=…)` | Wheel |
| `click_text("Save")` | Find AX button → press or click its center |
| `type_text("hello")` | Type unicode |
| `hotkey("cmd", "s")` | Shortcuts |

### Still on the roadmap

| Wanted | Today |
|--------|--------|
| Act without stealing focus | Foreground HID for now; background path planned |
| Fancy branded cursor chrome | Ice halo + status\|Stop chip (driven app) |
| Parallel multi-app sessions | Single session |

---

## Why AX-first (the efficient path)

**Slow loop:**  
screenshot → vision model → guess coordinates → click → repeat  

**Fast loop:**  
read Accessibility tree → `"Save" button at …` → `AXPress` or click center → done  

Vision still helps for games/canvases. For Settings, TextEdit, Safari chrome, Finder — **AX wins**.

---

## Permissions

| Permission | Why |
|------------|-----|
| **Accessibility** | Read UI tree + inject mouse/keyboard |
| **Screen Recording** | Window screenshots |

`desktop-harness --doctor` checks both.

---

## How Grok Build uses it

```bash
desktop-harness <<'PY'
print(mouse_pos())
move_to(400, 300)
wiggle()
click_text("Button Name")  # when visible
PY
```

You see the pointer move on your display while that runs.

Other agents call the same CLI from their shell tools.

---

## Safety

This is your **real** Mac and **real** mouse.

- Ask before send / post / pay / delete  
- Prefer shell for code work; GUI only when needed  
- You can yank the mouse anytime — human always wins physically  
