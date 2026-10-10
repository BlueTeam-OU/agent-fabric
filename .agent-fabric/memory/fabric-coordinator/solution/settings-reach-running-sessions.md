---
role: "fabric-coordinator"
class: solution
topic: "settings-reach-running-sessions"
description: "A key the settings writer puts in ~/.claude/settings.json reaches every RUNNING session at the next upgrade, not the next launch; tui switched renderers live and blanked the fleet's screens"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a028a69303d9f90a
---

## A key the settings writer puts in ~/.claude/settings.json reaches every RUNNING session at the next upgrade, not the next launch; tui switched renderers live and blanked the fleet's screens

`fabric-ctl all upgrade fabric` runs bootstrap, which runs
runtime/claude-code/user-settings.py and rewrites each account's
~/.claude/settings.json. Claude Code applies at least some keys live: after
#56 (a4ffc66, 2026-09-28) pinned `"tui": "default"`, every running session
switched from the alternate-screen renderer to the normal one mid-session;
the owner saw black screens with only new output. A relaunch (the owner
restarted architect-cto-01) fixed display and toolbar. Nothing was lost.

**Why:** the brief's "a session is fixed at exec" holds for the prompt,
model and binding, not for user settings the harness watches.

**How to apply:** before distributing a change to user-settings.py, test
it by rewriting the key under a live session of another login, and plan
the relaunch (say it in the PR and to the owner) when the key is a
display one.

*Observed 2026-09-28 (fabric-coordinator)*
