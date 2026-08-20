# Observe loop — after you build something visible

Everyday harness control (open, click, type) does **not** use this.
Use it when you **just built or changed** the pixels (a page, overlay, demo).

```
run → use like a person → capture → read the PNG → fix → again (max 3)
```

Do not say “looks good” without reading a capture.  
Do not vision-loop every click — AX first, then one look at the result.

```bash
desktop-harness -c 'print(screenshot(app="Google Chrome"))'
# then read that PNG
```

Web: `open -a "Google Chrome" <url>`. Hide presence when the pass ends.

## Presence UI specifically

**Dense capture (required for motion bugs):** one screenshot is not enough.
Take many frames while moving so lag/desync shows up:

```bash
./scripts/observe-demo.sh /tmp/dh-observe
# then read several frames: hold, mid-move, click
```

## Checklist for presence

- [ ] **One** cursor only — soft halo around system pointer, never a second arrow  
- [ ] Halo locked to warp target (no “dragging a second cursor”)  
- [ ] Move = ice ring; click = brief amber then ice  
- [ ] Chip sits **outside** the driven window; only the **Stop** zone is hittable  
- [ ] Chip shows driven **app name** (or "Agent") and a clear **Stop** — not one ambiguous label  
- [ ] Multiple frames reviewed, not one still
- [ ] **A click lands on a different app mid-sequence, and the demo keeps
      going for several more seconds afterward.** Confirm via frames taken
      *after* that click that the halo/banner are still visible. A demo
      that never gives up focus will pass even when this is broken — it
      shipped that way once already (2026-08-11: banner and halo silently
      stopped rendering the instant any other window became key, because
      the accessory app's run loop was never being pumped outside of
      show()/click_flash(); move() — the highest-frequency caller — pumped
      nothing at all).
- [ ] **Several seconds of pure idle** (no move/click calls, just a wait)
      immediately after that same focus-stealing click. Confirm the
      overlay is still there afterward, not just immediately after the
      click. A fix that only covers "during active motion" is not the
      same bug as "while sitting idle," and the second is the more common
      real case (an agent pausing between steps).
- [ ] If a fix here reaches for a background thread to keep something
      updating during idle time: don't. AppKit hard-aborts the whole
      process (SIGABRT, no Python exception, unrecoverable) when window
      methods are called off the main thread — confirmed by trying it.
      Chunk the wait on the calling thread instead (see
      `presence.keep_alive()`).
