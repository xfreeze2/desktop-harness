# Security

`desktop-harness` can control a real Mac (mouse, keyboard, UI). Treat it like granting Accessibility to a new app.

## Runtime protections

| Control | Behavior |
|---------|----------|
| `DH_ALLOW_SENSITIVE` | Default off. Blocks open/focus, mutations (click/type/hotkey), **screenshots**, and **clipboard get/set** while password-manager-like apps are targeted or frontmost — the clipboard is where a password manager puts the secret. |
| Audit log | `~/.desktop-harness/audit.jsonl` for key mutations (clipboard records length only, never contents) |
| Warm daemon | Unix socket **mode 0600** + **token** at `~/.desktop-harness/daemon.token` (0600 from the first byte). Requests without the token are rejected. Single-instance via **flock** on the pid file (a ping is not used — a busy daemon cannot answer one). Accepted connections time out so a hang before auth cannot wedge the Stop chip. |

The daemon is a **local privileged exec endpoint** (it can run harness scripts with Accessibility). Only your user account should read the token/socket. Do not run the daemon on shared multi-user machines without understanding this.

## Voice scaffold (`scripts/voice_session.py`)

This is a **separate** opt-in path (Grok Voice → tool calls → harness). It is
**not** covered by the main CLI alone:

| Mode | Flag | Behavior |
|------|------|----------|
| Dry-run | `--dry-run` | No Mac mutations; prints planned tool calls |
| Read-only (default) | _(neither)_ | `list_apps` / `screen_labels` / `mouse_pos` only |
| Live | `--live` | Mutating tools (`click_*`, `type_text`, `hotkey`, `open_app`, mouse) allowed |

Mutating tools **refuse in code** without `--live` — consent is not left to the
model prompt. Still: never pass `--live` for unattended use, and agents must
ask before send/post/pay/delete even when live.

## Recommendations

- Only install from a source you trust  
- Review agent scripts before `always-approve` / unattended runs  
- Keep default sensitive-app blocks; do not set `DH_ALLOW_SENSITIVE=1` casually  
- Agents should refuse outbound actions (messages, purchases, deletes) without human confirmation  
- Prefer `desktop-harness daemon stop` when finished with a long session  
- Voice: start without `--live`; add it only after the user clearly wants GUI control

## Reporting

Open a GitHub issue for vulnerabilities. Do not file public issues that include secrets or personal screen contents.
