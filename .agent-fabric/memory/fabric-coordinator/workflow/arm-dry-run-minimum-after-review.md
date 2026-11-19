---
role: "fabric-coordinator"
class: workflow
topic: "arm-dry-run-minimum-after-review"
description: "fabric-pr arm --dry-run on an unreviewed head refuses on the review gate before it prints the work-commit minimum; fabric-pr gate gives the counts but no minimum"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bf9008f81dcd8eea
---

## fabric-pr arm --dry-run on an unreviewed head refuses on the review gate before it prints the work-commit minimum; fabric-pr gate gives the counts but no minimum

On #538 (2026-11-10, head 6fb07543, not yet reviewed), `fabric-pr arm --dry-run 538 --basis "..."` printed
only "not a security-boundary change" and then REFUSED for the missing claude review. It never printed
the minimum. Without `--basis` it stops sooner ("--basis is required"). `fabric-pr gate 538` gives the
counts ("3 work, 0 fix, 1 merge"), checks and review state, but no minimum.

**Why:** the Stop hook (pr-counts.py) asks for "#N (W work, F fix)" in any reply that states a PR's
status. Those numbers come from `fabric-pr gate`. The minimum can be quoted only after the review is
posted.

**How to apply:** before the review, report the counts from the gate and say the minimum is not read
yet. Never quote the minimum from memory. Related: [[arming-prs]], [[pr-counts-for-every-pr-named]].

*References: arming-prs, pr-counts-for-every-pr-named*

*Observed 2026-11-09 (fabric-coordinator)*
