---
role: "fabric-coordinator"
class: solution
topic: "j481-assembler-same-run-claims"
description: "assembler same-run defects (InterWeave #516 F1/F2) — contract D1-D4 sent to python-dev-04 2026-10-31"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5ad4e47432240d7c
---

## assembler same-run defects (InterWeave #516 F1/F2) — contract D1-D4 sent to python-dev-04 2026-10-31

The 2026-10-28 InterWeave drain (j403, #516 review 5716071440) showed four assembler defects. All were read from the code at origin/main f89abb98 and confirmed against claims/architect-cto.json in ~/drain/2026-10-28-j403/interweave.tar and against the first-run report at InterWeave c8f9ed2d:
- D1: claim 57 got a same-agent supersede of heading H, and claim 56 (from another memory) named H as its merge_target. resolve_targets moved 56 into 57's topic, the pre-pass skipped it (collisions.py:97), and write_slice applied 56 over 57's fresh text. 57's lesson was lost. The only trace was an applied_corrections replaced_key for a text that never stood.
- D2: the description comes from group[0].title (writer.py:602, 506), so it named a heading that was gone.
- D3: a 140-like claim equal to part -2's H was judged "standing" (collisions.py:119). The same run's correction (149) replaced that H. In part 1 the claim then came back as "H (2)" with a collisions: key.
- D4: a heading held by two budget parts of one topic: which part a merge_target hits depends on split_by_budget.
REQUEST 01a19094-2acb (seq 690948) went to python-dev-04 for a for/user/j481-assembler-same-run-claims branch. j481 is blocked on it. Once it is delivered, fold it into my agent-fabric PR.

2026-10-31 (session cea4dd7d): D1-D4 (a28358fc) and j485 (0fa284dc) folded into #437 (merge c23c7f3e). Round 3 marked their files "not read" (it treated them as main-merge content), so round 4 was a full review: review 5722055086 on e31e795d read every path, with no finding on the assembler. Suite on e31e795d: FAILED_SUITES=0, red only on the sibling corpus lint. Round 4: F9 (review_brief render's second read) fixed in 2f8901c1. F8 (arm_findings same-chain, same-head judgement) went to devex-tooling as REQUEST 01a19127, and j481 is blocked on it. The reviewer's one-line fix would have dropped an H..H adjudication's judgement, so the contract says "unless its base is that head". Next: fold their commit, run the suite, re-review, then arm once F2 clears (python-dev-02's installer PR on main).

*Anchors: `tools/fabric/assembler/collisions.py::check_collisions`, `tools/fabric/assembler/writer.py::write_slice`*

*Observed 2026-10-31 (fabric-coordinator)*
