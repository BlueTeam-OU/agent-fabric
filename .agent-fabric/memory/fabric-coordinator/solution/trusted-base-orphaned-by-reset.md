---
role: "fabric-coordinator"
class: solution
topic: "trusted-base-orphaned-by-reset"
description: "A store's trusted base orphaned by a reset or rebase refuses the launch for every role; the agent repairs it with fabric-secrets store trust-base --replace-orphaned"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3eed053d807b8fe3
  - 9b924e1bf1cb153f
---

## A store's trusted base orphaned by a reset or rebase refuses the launch for every role; the agent repairs it with fabric-secrets store trust-base --replace-orphaned

On 2026-10-17 two agents would not launch: `agent-fabric.trustedbase` in their store's .git/config named a
commit HEAD no longer descended from (a reset after a failed push); the owner set both bases by hand in each
agent's pane.

Fixed in the tree on 2026-10-18 (`tools/fabric/secretstore/trust.py`): a store write that orphans the trusted
base moves it back, and the refusal names the repair, `fabric-secrets store trust-base --replace-orphaned`,
which re-trusts only after a rewrite that orphaned the base and only to the verified tip.

**Why:** auto mode refuses my setting another account's base ("Security Weaken"); the store is that agent's.
**How to apply:** when a launch refuses on the trusted base, the agent itself (or the owner in its pane) runs
the command the refusal prints; verify first that HEAD equals origin/main and is signed by the agent's own key.
Related: [[tmpdir-in-home-2026-10-17]].

*References: tmpdir-in-home-2026-10-17*

*Anchors: `tools/fabric/secretstore/trust.py::--replace-orphaned`*

*Observed 2026-10-23 (fabric-coordinator)*
