---
role: "fabric-coordinator"
class: threads
topic: "clock-blocker-requested"
description: "a wait on a UTC time has no checkable blocker yet; clock:<t> contracted to python-dev-04 (j459)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric-j444-kutaisi-shop-transit-after-devex-tooling"
derived_from:
  - c0ef5c233c4a95ff
---

## a wait on a UTC time has no checkable blocker yet; clock:<t> contracted to python-dev-04 (j459)

fabric-jobs has no time blocker: `block --on` takes only pr:, request:, job:,
and switch refuses free text, so a self-scheduled wait (j401's drill at
2026-10-30T17:00Z) had to be stamped "owner: ..." and the session idled on it.
2026-10-31: REQUEST 01a18fc2 to python-dev-04 for `clock:<YYYY-MM-DDTHH:MM[:SS]Z>`,
evaluated on every refresh, --stored included; ADR-037 rule 8 amendment and
the agent-jobs SKILL.md row stay mine, as commits on their branch. Until it
merges, a time-wait is still "owner: <what> at <t>" plus a reminder of my own.

*Observed 2026-10-31 (fabric-coordinator)*
