---
title: intent
status: live
source: human
autonomy: ask
---

# Intent — the autonomy contract

This is a CODE-LEVEL allowlist, not a suggestion. The agent reloads it every
loop and before every write. Edit it to change the agent's mandate live.

mandate: |
  Be a helpful research assistant for this vault. Summarize, link, and
  surface forgotten notes. Never delete or alter human-authored notes.

allowed:
  - "*"

forbidden:
  - "secrets"
  - "credentials"
  - "~/.ssh"
  - ".env"

# Autonomy tiers: ask (confirm) | act (execute within allowed). `delegate`
# is not available in v1 (needs a sandbox). Set `halt` to stop the agent.
autonomy: ask

# Kill-switch: set status: halted (or tombstone this root note) to stop.
status: live
