---
role: "fabric-coordinator"
class: workflow
topic: "own-checkout-is-fleet-tooling"
description: "~/projects/agent-fabric is both my working copy and the fabric my login runs (fabric-ctl, hooks, the owner's Fleet Deck): a feature branch there, behind main, runs old code for everything on this login"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2cdc4d7f39d9b346
---

## ~/projects/agent-fabric is both my working copy and the fabric my login runs (fabric-ctl, hooks, the owner's Fleet Deck): a feature branch there, behind main, runs old code for everything on this login

2026-10-10: with my checkout on a PR branch 30 commits behind main (before #170 merged
there), the owner restarted the Fleet Deck as `user`; its `fabric-ctl all states --follow`
resolved through my checkout and started the deleted Node `ctl.mjs` again. `fabric-ctl all
upgrade fabric` also refuses my account while it is off main.

**Why:** ~/.local/bin links into this checkout, and the owner's tools run on the `user` login.

**How to apply:** work on a branch only briefly; switch back to main before anything the owner
or the fleet runs through this login (a Deck restart, an upgrade, a hook). Prefer a separate
worktree for long branch work. And never `pkill -f` a pattern that also appears in the
command line running it: it killed my own shell (match a PID, or `pgrep -f` then filter).

*Observed 2026-10-10 (fabric-coordinator)*
