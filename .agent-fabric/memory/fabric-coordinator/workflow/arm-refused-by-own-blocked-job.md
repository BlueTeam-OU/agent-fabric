---
role: "fabric-coordinator"
class: workflow
topic: "arm-refused-by-own-blocked-job"
description: "fabric-pr arm refuses while a job of yours on the PR's branch is still \"blocked\", even after its blockers cleared; deliver it with the PR first"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "kutaisi-shop-transit"
    working_copy: "kutaisi-shop-transit"
derived_from:
  - fd5b3f340ad908b8
---

## fabric-pr arm refuses while a job of yours on the PR's branch is still "blocked", even after its blockers cleared; deliver it with the PR first

`fabric-pr arm` (gate 4c's job check) refuses a PR when a job on its branch is in state `blocked`
with a free-text blocker, even when that blocker has in fact cleared — it cannot check free text.
Seen 2026-11-14 on gzapi-org/[redacted]-shop-transit#5: j505 was blocked on "owner's word + fabric-repo-policy
apply for fabric/armed"; both had cleared (owner's word 2026-11-13; `fabric-repo-policy verify` matched).

**Why:** a free-text blocker never clears by itself; only a checkable one (`--on pr:/job:/request:/clock:`) does.

**How to apply:** verify each blocker against the source (the ruleset, the owner's message), then
`fabric-jobs deliver <job> <owner/repo>#<n>` — the PR is the job's artifact — and re-run the dry-run.
Use `--defer-job` only when the job's wait is not this PR's. When blocking a job on a PR's own
prerequisites, prefer checkable `--on` blockers so the next arm does not trip on stale text.
Related: [[frontmatter-origin-not-redacted]].

*References: frontmatter-origin-not-redacted*

*Anchors: `agent-fabric:tools/fabric/github/arm.py::unblock it (fabric-jobs)`*

*Observed 2026-11-14 (fabric-coordinator)*
