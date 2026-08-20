# Release checklist (v0.6.6)

## Must pass

- [ ] `desktop-harness --doctor` all PASS  
- [ ] `desktop-harness selftest` all PASS  
- [ ] `desktop-harness demo` — mouse moves, TextEdit types; status|Stop chip visible  
- [ ] AX-only `click_text` still shows the Stop chip (no mouse move required)  
- [ ] No secrets in repo  
- [ ] `git push` to https://github.com/xfreeze2/desktop-harness  

## Agent integration

- [ ] Skill installed: `~/.grok/skills/desktop-harness/SKILL.md`  
- [ ] Optional rule: `~/.grok/rules/desktop-harness.md`  
- [ ] `desktop-harness` on PATH  

## Known limits (honest)

- Not full background multi-cursor (focus may move to target app)  
- Electron / some web apps: sparse AX → may need screenshots  
- Media: always `media_transport` / `ensure_media_playing` — never spam Space  
- Real Mac risk: agents must ask before send/pay/delete  

## After public attention

- Prefer issues with `desktop-harness --doctor` + `selftest` paste  
- Do not request CAPTCHA / Cloudflare bypass features  
