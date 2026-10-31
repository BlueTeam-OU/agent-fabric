---
role: "fabric-coordinator"
class: workflow
topic: "owner-defers-findings-to-bugfix-pr"
description: "Owner 2026-10-17: a PR stuck in review rounds merges after the next review anyway; its open findings go to one later bug-fix PR"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 033bea8cdd7bb6c3
---

## Owner 2026-10-17: a PR stuck in review rounds merges after the next review anyway; its open findings go to one later bug-fix PR

On InterWeave #286 (swipe spec, eight review rounds, each finding smaller focus-table gaps) the owner said: "move on and merge after the next review anyway - so we can merge also the following pr. then at the end will take on again these issues all together in a bug fix pr."

**Why:** review rounds on a spec kept converging slowly while the PRs behind it waited; throughput beats closing every P2 on one PR.
**How to apply:** when the owner says so, arm after that review with its open P2/P3s deferred, the basis naming the deferral, and file them at once as a job for the bug-fix PR (owner's word, lane owner per finding). A P1 (data lost or sent unchosen) still goes back to the owner before arming. Never assume this for another PR without the owner saying it. See [[owner-arm-only-when-verified]].

*References: owner-arm-only-when-verified*

*Observed 2026-10-17 (fabric-coordinator)*
