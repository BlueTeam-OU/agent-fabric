---
role: "devex-tooling"
class: solution
topic: "gate4c-adjudication-shape"
description: "How a finding from any earlier review round is closed (gate 4c adjudication): shape, readers, why not a chain"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 21f4f6edf713d809
---

## How a finding from any earlier review round is closed (gate 4c adjudication): shape, readers, why not a chain

An ADJUDICATION closes a finding that `fabric-pr arm` gate 4c holds open from an earlier round (j329, REQUEST 01a1cf77,
commit 0f6a2e43 on develop-qzapp/devex-tooling/for/user/gate4c-adjudication-any-round):

- v2 review, marker base = the head the finding was raised on, head = a later commit (never base == head);
- machine lines only `Judgement:` + `Finding: none`; each judged label must be raised on that base head;
- post-review accepts it only when the base is neither merge-base nor checkpoint head, and stamps
  `review_coverage.ADJUDICATION_LINE` as line 2; `review_coverage.is_adjudication` is the one reader.
- arm_findings: its judgements touch only findings raised on its base head (any chain), never its own head's; it joins
  no chain; one raising a Finding is unknown. review_checkpoint sets adjudications aside before the newest decides.

Why not just reuse chain continuation (base=H already joined H's chain): the chain cannot tell apart two rounds that both
number an F1 (newest open wins), and moving chain_of_head[X] to an old chain hides later chains. A test that looked
right (round 1 of 3, separate chains) passed at base too; the same-chain two-F1 case is the one that discriminates.
Brief/next rendering of it is fabric-coordinator's (review_brief.py / review_rounds.py are on the never-list).

*Anchors: `tools/fabric/github/review_coverage.py::ADJUDICATION_LINE`, `tools/fabric/github/arm_findings.py::_adjudicate`, `tools/fabric/github/post_review.py::adjudication_refusal`*

*Observed 2026-11-12 (devex-tooling)*
