---
role: "python-dev"
class: workflow
topic: "answers-trailer-marks-a-fix"
description: "never put Answers: on a work commit — pr-gate counts any commit carrying it as a review fix, dropping the work count below the arming threshold"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 41eeb75a0c3898ac
---

## never put Answers: on a work commit — pr-gate counts any commit carrying it as a review fix, dropping the work count below the arming threshold

pr-gate.sh (runtime/github) classifies a commit as a review FIX when it
carries an `Answers:` trailer (the primary signal), whatever its subject.
On #110 (2026-10-07) the item commits carried `Answers: GZCoord REQUEST …`
and the cherry-picked commits kept theirs from earlier deliveries: the gate
counted 4 work / 10 fix where 11 were work, so the PR fell under the
8-work threshold and arming became the owner's.
**Why:** the work count decides who arms (≥8: me at the gate; fewer: the owner).
**How to apply:** cite a REQUEST in the body text ("…answers REQUEST <id>, item 3"),
never as `Answers:`; keep `Answers:` for review fixes only. When carrying
commits from an old branch, check their trailers before opening the PR.
Related: [[trailer-block-must-be-one-line-per-key]].

*References: trailer-block-must-be-one-line-per-key*

*Observed 2026-10-07 (python-dev)*
