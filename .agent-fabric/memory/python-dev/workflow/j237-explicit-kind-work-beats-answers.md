---
role: "python-dev"
class: workflow
topic: "j237-explicit-kind-work-beats-answers"
description: "a review-fix commit carries Answers: and NO Kind line; an explicit Kind: work wins and the gate counts it as work (j237, #589)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5384eee1d2c4f1b3
---

## a review-fix commit carries Answers: and NO Kind line; an explicit Kind: work wins and the gate counts it as work (j237, #589)

In j237 I gave both review-fix commits `Kind: work` plus `Answers: F1…`; the commit-msg hook stamps review-fix only when no Kind is given, so the gate counted them as work (#589 overstated by 2). The job guard then refused a reword once the job was delivered, so the miscount had to be stated in the PR description.

**Why:** the coordinator corrected it by message (seq 1093215); the correction came after `fabric-jobs deliver`, when commits are blocked.
**How to apply:** a commit answering findings carries `Answers:` and no `Kind:` line; check `git log -1 --format=%B` before pushing a for/ branch, not after delivering. Also: a second report writer (record_rehomed) must update keys in place, since merge_reports' other-stamp branch drops harvest/memory/horizon fields (F6, j238). See [[answers-trailer-marks-a-fix]].

*References: answers-trailer-marks-a-fix*

*Observed 2026-11-13 (python-dev)*
