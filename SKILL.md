---
name: desktop-harness
description: >
  Control the user's real Mac desktop: open apps, click UI, type, move the mouse,
  read Accessibility labels, take window screenshots. Use whenever a task needs
  the Mac GUI (System Settings, native apps, installers, "click this", "open that
  app", "type into the field", computer use, desktop control, laptop automation).
  Invoke the local CLI `desktop-harness` (not MCP). Prefer AX labels over screenshots.
---

# desktop-harness

**Product:** local CLI that gives coding agents real Mac control.  
**Not MCP.** Invoke via shell. Optional warm daemon for multi-step speed.

You **do** have this capability when the skill is installed and `desktop-harness` is on PATH.
Use it proactively for Mac GUI tasks — don't say you can't control the laptop.

## When to use

- Task needs a **Mac GUI** (Settings, native apps, installers, no good CLI)
- User asks you to open/click/type on the Mac, or "use desktop-harness"

## When not to use

- Files, git, brew, HTTP APIs → shell / other tools first  
- Anything that doesn’t need the Mac GUI

## Setup check (once per session if unsure)

```bash
desktop-harness --doctor
# daemon auto-starts on first script (DH_AUTO_DAEMON=0 to disable)
desktop-harness daemon status
```

## Efficiency (mandatory)

1. Shell before GUI  
2. **`labels` / `find` / `click_text` first** — cheap, targeted AX reads  
3. Prefer `AXPress` path (`click_text`) over coordinates  
4. Multi-step work → start/use the warm daemon  
5. Never vision-loop by default  
6. **`ax_snapshot` is a debug aid**, not the default eyes — a full snapshot is often ~10× more tokens than a screenshot and far more than `labels(limit=30)`. Use it when debugging why a find failed or you need raw roles/frames; cap `max_nodes` tightly. Everyday control should not dump the tree.

## Usage

```bash
desktop-harness <<'PY'
print(frontmost_app())
print(labels()[:20])          # cheap default read
print(find("Reload")[:3])     # targeted; JSON-safe (no raw AX refs)
open_app("Safari")
click_text("Bookmarks")
PY
```

```bash
desktop-harness demo    # visible smoke test
desktop-harness --doctor
```

If a daemon is running, the CLI auto-routes scripts through it (faster).  
`DH_NO_DAEMON=1` forces a fresh process.

## Helpers

- Discovery: `list_apps`, `list_windows`, `frontmost_app`, `open_app`, **`window_frame(app?)`**
- See: `labels`, `button_labels`, `find`, `screenshot`, `media_transport`  
  (`ax_snapshot` = debug dump; prefer `labels`/`find`; menubar skipped by default)
- Act: `click_text(..., exact=False)`, `set_field`, `type_text`, `hotkey`, `key`  
  **`menu_click("File", "Save", app=?)`** — exact menu titles only (no fuzzy)  
  `click_text` **refuses** a weak, huge, or neck-and-neck match instead of
  guessing (that was accidental clicks). Prefer `exact=True` for Play/Save/OK.  
  A click is also refused if the mouse moved without the harness — you have
  the pointer; it will not click over you.
- Media: `now_playing(app?)` (title + state, no click);  
  `ensure_media_playing(app?)` — **look once, act once**;  
  `media_key("playpause"|"next"|"prev"|"volumeup"|"volumedown"|"mute")`
- Mouse: `mouse_pos`, `move_to`, `wiggle`, `click`, `click_frame`, `drag`, `scroll`  
  Window-local (screenshot space): **`click_in_window(x,y,app?)`**, **`drag_in_window(...)`**, **`win_to_global`**
- Hold / instant: **`keys_hold([...])`**, `key_down` / `key_up` / `release_keys`, **`tap(x,y)`** (no settle)
- **Fast eyes (any window, no PNG):** `grab_frame(app?, region?)` → RAM `{w,h,data,x,y}`; `pixel`;  
  `find_color(frame, rgb, tol=, region=)` · `count_color` · `scan_column` / `scan_row` · `largest_run`  
  A named-app grab never silently becomes a full-desktop shot.
- **When the next frame matters:** do **not** screenshot → chat → click.  
  `run_loop(step, app=, hz=30, seconds=12)` — `step` returns an action dict  
  (`hold`, `key`, `tap`, `tap_win`, `scroll`, `stop`). One process. Stop chip still aborts.
- **Batch:** `run_plan([{op, ...}, ...], app=?)` — many steps in one process (prefer over N CLI calls)
- **Stage (web, off-to-the-side):** `open_stage(url)` / `close_stage()` — small dedicated Chrome + a live picture **only** for that window. Do **not** `show_monitor()` when the real app is already on screen.
- **Control session:** ice ring + ice frame + status|**Stop** chip (shows the driven app).
  Mutating helpers auto-show presence so Stop is always hittable — including
  AX-only paths that never move the mouse. Prefer an explicit session for
  multi-step turns:

  ```python
  begin_control("Notes")   # chip + ring up before the first click
  click_text("All iCloud")
  # …
  end_control()            # hide when done (also auto-clears ~20s idle)
  ```

  Off: `DH_PRESENCE=0`. No second picture of an on-screen app.
  `enable_agent_cursor` / `hide_agent_presence` still work (aliases).
  **Stop is a real abort.** It hides presence and raises `ControlStopped`.
  After a stop, do not continue. On a later user request, call
  `begin_control()` or `resume_control()` first.
- Clipboard: `clipboard_get()` / `clipboard_set(text)` — plain text only.
  Both are gated: a Stop click aborts them, and both refuse while a password
  manager is frontmost (same rule as an unscoped screenshot).  
- Meta: `wait`, `wait_stable`, **`wait_for(text, app?, timeout=3)`** — poll AX
  until a control appears (dialogs/sheets). Not a screenshot loop.
  `verify(note, app?)` — screenshot + AX only when failure would be silent.

## Which loop to use (efficiency + capability)

| Situation | Use |
|-----------|-----|
| One or two AX actions | `click_text` / `set_field` / `menu_click` (daemon auto) |
| Many steps, same turn | **`run_plan([...])`** — one process, no N CLI spawns |
| Next **frame** is the action | **`run_loop(step, hz=…)`** — never screenshot→chat→click |
| Just built visible UI | Observe loop (`docs/OBSERVE-LOOP.md`) — not everyday clicks |

## Live view — only when they cannot already see it

If Notes / Settings / YT Music is **on screen**, do not open a second
picture of it. The user is already watching. Presence (ice ring +
status|**Stop**) is enough.

Use `open_stage(url)` **only** for a web task that should not take over
the user’s Chrome or the whole display. That helper opens a small
dedicated window *and* the live view of *that* window — then
`close_stage()` when done.

```python
# everyday: just control the real app
begin_control("Notes")
click_text("All iCloud")
end_control()

# web, off to the side:
open_stage("https://example.com")
# …act only on stage_frame()…
close_stage()
```

## Prefer what's already open

Before opening a browser tab or launching a new instance of anything: run
`list_apps()` / `frontmost_app()` / `list_windows()` first and check for a
native app that's already open and matches the task (Spotify, YT Music,
Mail, Notes, Music, etc). Control that instance directly — it's faster and
it's what the user is looking at. Only fall back to a browser when no
matching native app is open, the native app genuinely can't do what's asked
(e.g. no in-app search for a specific track), or the user's request needs an
exact URL. Opening Chrome to a web version of something that was already
open and visible on screen is the single most confusing thing this harness
can do — it looks like the agent didn't see what the user saw.

## Verify, don't assume — but only where failure is silent

`click_text` / `set_field` already raise if there's no AX match, and
`ensure_media_playing()` re-reads state after pressing — for a normal
click, field edit, or app switch, that's the check: no exception plus (when
it matters) a follow-up `labels()`/`ax_snapshot()` read is enough. Calling
`verify()` — a screenshot + AX read — after **every** UI-changing action
brings back exactly the vision-loop tax Efficiency rule 5 says not to pay,
for no real benefit on the 95% of actions that fail loudly.

Call `verify(note, app?)` — and **read the screenshot path it returns** —
only when the action could succeed at the AX layer while doing the wrong
thing, with no other way to notice:

- **Media transport** (play/pause/skip/next): a toggle that "succeeds"
  whether it played or undid what you just started looks identical without
  a look. This is what actually broke in `docs/POSTMORTEM-media-play.md` —
  not a missing screenshot, but pressing a matched-but-wrong control with
  no re-check. Prefer `ensure_media_playing()` (built-in re-check) over a
  raw click here; reach for `verify()` if you're doing something media the
  helper doesn't cover.
- **Anything already gated under Consent below** (messages, posts,
  purchases, deletes, security/privacy settings, passwords) — confirm the
  real outcome before telling the user it's done; getting these wrong is
  costly, not just annoying.
- A step you're about to report as finished where being wrong would send
  you down a materially different fix.

Skip it for routine navigation, discovery calls (`labels`, `ax_snapshot`),
and clicks whose result you can already see in the return value.

## Media / players (learn from mistakes)

When the user says “play the song on screen”:

1. Prefer the **already-open** player (`list_apps` / `frontmost_app`) — e.g. **YT Music**, not a new Chrome tab.  
2. **Read state first:** `media_transport(app?)` or look for exact **Pause** / **Play**.  
   - **Pause visible** → already playing → **stop**. Do not click again.  
3. **One action only:** `ensure_media_playing(app?)` (AX Play, else one system `media_key`).  
4. **Never** spam `hotkey("space")` or multi-retry loops — Space **toggles**.  
5. **Never** match loose `"Play"` against **Play all** / **Playing from**.  
6. YT Music is a **Safari Web App** — AX often has **no** Play button; `ensure_media_playing` / `media_key` is correct, not a long AX thrash.  
7. Changing track requires an **explicit** user request.

## Consent / safety

Real Mac. **STOP and ask** before: messages, posts, purchases, deletes, security settings, passwords.  
Harness also blocks password-manager-like app names unless `DH_ALLOW_SENSITIVE=1`.

## Canvas / custom-drawn apps (Canva, Figma, games)

AX labels often cover **chrome only** (tabs, menus), not objects on the
canvas. That is not a harness failure — the OS tree has nothing useful to
click. Path without losing capability:

```python
fr = window_frame("Canva")
path = screenshot(app="Canva")
# …vision/plan on the image (window-local px)…
run_plan([
    {"op": "drag", "wx1": 100, "wy1": 200, "wx2": 400, "wy2": 300},
    {"op": "drag", "wx1": 500, "wy1": 200, "wx2": 700, "wy2": 300},
    {"op": "hide_presence"},
], app="Canva")
```

1. `window_frame` + `screenshot` once → read image (vision / parallel perception)  
2. Coordinate actions in **window-local** px via `click_in_window` / `drag_in_window` / `run_plan`  
3. **One** daemon `run_plan` (or one long script) — not N CLI spawns  
4. Do **not** dual-agent the same pointer — one Mac, one cursor  

If the next **frame** is the action (canvas, video, live playhead, anything
that is gone if you wait a second): do **not** screenshot → chat → click.

```python
cream = (230, 220, 210)
def step(frame):
    hit = find_color(frame, cream, tol=30, region=(0.1, 0.2, 0.4, 0.6))
    if not hit:
        return {"hold": []}
    return {"hold": ["w"] if hit["y"] > frame["h"] * 0.55 else ["s"]}
run_loop(step, app="Google Chrome", hz=30, seconds=12)
```

The **rgb / keys / region** are the task. The harness only sees pixels and
holds keys. Same primitives for a flyer, a timeline, a canvas, a player.

Parallel *perception* (subagent labels clusters on a saved PNG) is fine.  
Parallel *control* of one app is not.

## Gotchas

- Grant **Accessibility** + **Screen Recording** to the host that runs the CLI (`--doctor`)  
- Coordinate clicks want the target app frontmost  
- Electron apps may need screenshot fallback  
- Cap tree size — don’t dump full AX  
- Hotkeys: use `minus`/`equal` or `-`/`=`; also `[` `]` `home` `end` `pageup` `pagedown`

## After you build something visible (required)

Everyday open/click/type does **not** need a vision loop (see Efficiency).
When **you just built or changed** the thing on screen (a page, overlay,
app UI, demo), you are not done until you have used it and looked:

1. Run it (Chrome for web: `open -a "Google Chrome" <url>`).
2. Use it like a person (`labels` / `click_text` / `wait_for`).
3. `screenshot(app=…)` or `screencapture` — **read the PNG**.
4. Fix only real defects. Repeat at most twice more.
5. `end_control()` (or `hide_agent_presence()`). Claim only what the last capture shows.

Presence / motion extras: `docs/OBSERVE-LOOP.md`.

## Docs in repo

`README.md` · `HOW_IT_WORKS.md` · `DESIGN.md` · `docs/OBSERVE-LOOP.md`
