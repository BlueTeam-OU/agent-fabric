---
role: "fabric-coordinator"
class: workflow
topic: "arm-after-checks-not-during"
description: "fabric-pr arm does not gate on CI results: #247 armed with platform-smoke (debian) failed; arm only after every check reads pass"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2d9428e7777e805c
---

## fabric-pr arm does not gate on CI results: #247 armed with platform-smoke (debian) failed; arm only after every check reads pass

2026-10-14, #247: `gh pr checks 247 --watch; fabric-pr arm 247 …` armed the PR although
platform-smoke (debian) and ci-ok had failed — the arm checks the review gate, threads and counts,
not check results; auto-merge then simply waits on the red required check, and the arm basis posted
"CI green" falsely.

**Why:** an armed PR with a red check looks ready to the owner and to the board; the basis comment
is the record.
**How to apply:** after `--watch`, read `gh pr checks` and arm only when every line is pass/skipping
(else print what failed). Worth a devex-tooling request: arm refuses a head with a failed check.
Related: [[fold-then-ci-then-review-then-arm]], [[owner-arm-only-when-verified]].

*References: fold-then-ci-then-review-then-arm, owner-arm-only-when-verified*

*Observed 2026-10-14 (fabric-coordinator)*
