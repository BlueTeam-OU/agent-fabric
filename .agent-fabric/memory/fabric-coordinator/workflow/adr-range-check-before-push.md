---
role: "fabric-coordinator"
class: workflow
topic: "adr-range-check-before-push"
description: "Before pushing any commit that touches docs/adr/, run adr.py range-check on the branch; `check` alone passed twice on 2026-10-16 while CI went red"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 46e2cf7eecdff975
---

## Before pushing any commit that touches docs/adr/, run adr.py range-check on the branch; `check` alone passed twice on 2026-10-16 while CI went red

Before pushing a commit that touches docs/adr/, run `python3 tools/fabric/adr.py range-check $(git merge-base origin/main HEAD) HEAD`, not only `adr.py check`. Moving a row inside an Amendments table still counts as a body edit and needs a row or an `ADR-Editorial:` trailer.

It happened twice on 2026-10-16:
- 9266b09a on #280;
- b01a6130 on #283, red in CI on guards-and-suites. I fixed it by rewording the commit through `git rebase -i -r` with a GIT_SEQUENCE_EDITOR sed to "reword" and a GIT_EDITOR script that adds the trailer inside the trailer block, then force-pushed with a lease.

**Why:** this guard has CI and suite legs but no commit-time leg, so nothing stops the commit itself (job queued to add the hook).
**How to apply:** run range-check on every review-fix round that touches a record, before the push.

*Observed 2026-10-16 (fabric-coordinator)*
