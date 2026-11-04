---
role: "fabric-coordinator"
class: workflow
topic: "arm-reads-every-rounds-open-findings"
description: "before arming, read the job's blocker and every earlier round's judged-real findings — a fresh full review resets the gate, not the debt"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 74519c4799025fea
---

## before arming, read the job's blocker and every earlier round's judged-real findings — a fresh full review resets the gate, not the debt

2026-10-30, #425: round 2 (previous session) left F5 (P3, lease.py wait line) judged real with a supply REQUEST 01a18bf5 to python-dev-01, j412 blocked on it ("#425 waits on this before it arms"). This session's renderer refused a re-review, so I ran a fresh full review; it did not re-raise F5, the gate read "head reviewed", and I armed — #425 merged without F5. Follow-up: python-dev-01 supplies from d941d5b0.

**Why:** the gate judges only the latest review chain; open findings of a superseded chain and the PR's own job blockers are invisible to it.

**How to apply:** before `fabric-pr arm`, run `fabric-jobs show` for EVERY job whose branch is the PR's, and list Finding lines of all posted reviews minus their Judgement fixed lines. Guard gap to fix (job). Related: [[fold-then-ci-then-review-then-arm]].

*References: fold-then-ci-then-review-then-arm*

*Anchors: `tools/fabric/github/arm.py::smaller batches next time`*

*Observed 2026-10-30 (fabric-coordinator)*
