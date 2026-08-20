# desktop-harness — design

**Status:** v0.6.6  
**Built with:** Grok Build  
**Goal:** Let a coding agent control a real Mac desktop — fast, precise, local — without a screenshot→vision loop on every step.

Primary experience: **Grok Build** (CLI + skill). Compatible with other shell-capable agents.

---

## Why this exists

Coding agents are strong at shell and code, but weak at real Mac GUIs. macOS already exposes a **real accessibility tree** for native apps — that is the efficient way for an agent to “see” and act without burning vision tokens every click.

Public idea, local implementation:

| Layer | Role | Cost |
|-------|------|------|
| **1. Shell / APIs** | Prefer non-GUI when possible | ~0 ms vision |
| **2. Accessibility (AX) tree** | Primary eyes + element actions | ~tens of ms |
| **3. Window screenshot** | Fallback eyes when AX is empty/custom | ~50–150 ms |
| **4. OCR / vision** | Last resort for unlabeled pixels | expensive |

Screenshot→vision→pixel-click loops are capable but often **slow**. AX-first keeps capability and speed on real Mac apps.

---

## Product shape

Not an MCP server first:

- **CLI** `desktop-harness` that `exec`s Python with helpers in scope  
- **Skill** so **Grok Build** reaches for it automatically  
- Works from **any** agent/script that can run the CLI  
- **MCP wrapper later** if we want tool-shaped RPCs; the core stays a thin local library  

**SKILL.md has two on-disk copies that must stay identical:** repo-root
`SKILL.md` (what you edit) and `src/desktop_harness/data/SKILL.md`
(`pyproject.toml`'s `force-include`, the copy a built wheel ships). `desktop-harness
skill` reads repo-root first so an editable-install edit takes effect
immediately; the packaged copy is only the fallback for a real installed
distribution with no repo tree alongside it. Editing only one has drifted
silently more than once — when you change SKILL.md, copy it over
`data/SKILL.md` too (or run the two-line diff/cp in the repo root) before
committing.

---

## Architecture

```
agent (Grok Build / others)
  │  desktop-harness <<'PY' ...
  ▼
helpers.py          # public surface
  ├── windows.py    # list / focus / bounds
  ├── ax.py         # tree, find, press, set value   ← PRIMARY
  ├── capture.py    # window / region / display PNG  ← FALLBACK
  └── input.py      # CGEvent click / type / key     ← HANDS
```

Optional warm **daemon** for multi-step speed (token-authenticated local socket).

### Perception contract

1. **`labels` / `find` / `click_text`** — default eyes; targeted, cheap, JSON-safe  
2. **`ax_snapshot`** — full interactive dump for **debug only** (often far more tokens than a screenshot; cap `max_nodes`). **Menubar skipped by default** so node budget goes to windows; `include_menubar=True` when you need menus.  
3. **`screenshot` + `window_frame`** — window-scoped when AX is empty or custom-drawn; map px → global via `win_to_global` / `click_in_window`  
4. **`run_plan`** — multi-step actions in one process (efficiency without cutting ops)  
5. **`grab_frame` + `find_color` / `scan_column` + `run_loop`** — when the next frame is the action. RAM pixels, held keys, instant tap. No app-specific policy in the package.  
6. **`show_monitor` / `follow`** — live picture of the window being driven (any app). Optional **`open_stage`** = dedicated small Chrome for web only.  
7. Coordinates only when no AX action exists  

Note: `AXPress` works on a **background** app without focus steal — the AX path already delivers the “background control” roadmap item for pressable controls.

### Action contract

- `activate` / `open_app`  
- `click` / `type_text` / `hotkey` / `scroll`  
- Media: `media_transport` / `ensure_media_playing` (no Space spam)  

### Permissions

| Permission | Why |
|------------|-----|
| **Accessibility** | Read AX + post input |
| **Screen Recording** | Window capture fallback |

`--doctor` and `selftest` verify the chain.

---

## Efficiency rules (non-negotiable)

1. **Shell before GUI**  
2. **AX before pixels**  
3. **Window before full display**  
4. **Compact trees**  
5. **Element action before coords**  
6. **No vision loop by default** — `verify()` (screenshot + AX read) is
   reserved for actions where failure is silent (media transport,
   consent-gated steps), not a step after every routine click  
7. **Consent** before outbound / destructive actions  

---

## Roadmap

| Version | Deliverable |
|---------|-------------|
| **v0.1–0.3** | AX + mouse + daemon + safety + media helpers |
| **v0.4** | selftest, install.sh, public docs, Grok-first positioning |
| **v0.5** | Live **Agent view** monitor (any app) + optional Stage Chrome for web |
| **v0.6** | Reflex `run_loop`, presence ice frame + Stop chip, fail-closed clicks |
| **v0.6.6** | Control-session presence (AX-only too), status\|Stop chip, loop skill |
| **later** | Background focus-free control, optional MCP, permission onboarding app |

---

## Explicit non-goals

- Cloning any proprietary computer-use product  
- Sandbox / VM isolation by default (real Mac — consent matters)  
- Replacing shell tools for normal coding work  
