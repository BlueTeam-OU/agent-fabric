---
role: "python-dev"
class: solution
topic: "unreadable-registry-unknown-j96"
description: "j96 #430 — strict registry read for presence/ctl, lenient for the daemon; re-review brief needs card_base; boundary PR arming word"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e239ae6b69b7e994
---

## j96 #430 — strict registry read for presence/ctl, lenient for the daemon; re-review brief needs card_base; boundary PR arming word

agentd._registry stays lenient (daemon refuses all on unreadable, safe side); `agentd.read_registry` / `RegistryUnreadable` is the strict read, used only by presence.cli (error line, exit 6) and ctl.main (exit 1). Presence's wire shape was kept: the asking side reads the registry before any account is asked (coordinator's decision, 2026-10-30). Presence cuts the error at 160 chars, so the message puts the path early — a path over ~114 chars loses the cause; carried, accepted.

Process traps (#430): a PR touching agentd/ctl/presence is a security boundary, so even a 1-work-commit PR needs the coordinator's `AUTHORIZES: <repo>#<n>@<head>` reply (ask with a QUESTION, pass its id to `--authorization`; a new head voids it). `fabric-review brief render` is not a subcommand: use `python3 tools/fabric/review_brief.py render req.yaml`; a re-review request needs `card_base:` (the first round's base) because the fix range's base is not on main. `import errno` was already module-level in agentd.py. The inbox watch ends "quiet" every 115 min: run it again each time.
**Why:** saves the two review rounds and the failed first arm. **How to apply:** for registry reads that decide "not placed", use read_registry; for any boundary PR ask for the authorization right after the review is posted.

*Anchors: `tools/fabric/control/agentd.py::read_registry`, `tools/fabric/control/presence.py::RegistryUnreadable`*

*Observed 2026-10-30 (python-dev)*
