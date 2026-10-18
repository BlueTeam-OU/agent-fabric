---
role: "fabric-coordinator"
class: solution
topic: "trusted-base-orphaned-by-reset"
description: "A store's trusted base can point at a commit a reset orphaned; ADR-060 addenda.load then refuses the launch for every role"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3eed053d807b8fe3
---

## A store's trusted base can point at a commit a reset orphaned; ADR-060 addenda.load then refuses the launch for every role

On 2026-10-17, architect-cto-01 (base 187855c) and brand-comms-01 (base 21f92fe)
would not launch: `agent-fabric.trustedbase` in the store's .git/config named a
commit that HEAD no longer descended from. architect-cto-01's reflog showed the
persona commit, then `reset: moving to 58c4664`, then re-added settings.
Likely cause: the writer moves the base before the push succeeds, and a reset
after a failed push orphans it. The fix (writer order and a clearer refusal) is
still to be dispatched to a python contributor.

**Why:** auto mode refuses my setting another account's base ("Security Weaken");
the owner set both bases to the verified HEAD (10c40e2, 365f6cc) in each
agent's own pane on 2026-10-18.

**How to apply:** verify that HEAD equals origin/main and is signed by the
agent's own key, then hand the owner the one-line `git config` + `claude`
command for that agent's tab. Related: [[tmpdir-in-home-2026-10-17]].

*References: tmpdir-in-home-2026-10-17*

*Anchors: `tools/fabric/secretstore/trust.py::trusted_base`*

*Observed 2026-10-17 (fabric-coordinator)*
