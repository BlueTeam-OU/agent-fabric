---
role: "devex-tooling"
class: solution
topic: "arm-findings-same-head-engines"
description: "arm_findings gate 4c — two engines reviewing one head on one base start two chains; an earlier-chain judgement skips findings on its own head"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - be92e007390fc748
---

## arm_findings gate 4c — two engines reviewing one head on one base start two chains; an earlier-chain judgement skips findings on its own head

In tools/fabric/github/arm_findings.py read(), chains join by base= matching an earlier head=, so Codex and
Claude both reviewing H1 on base B (B never a review head) start two separate chains, both numbering from F1.
A judgement whose own chain never raised the label goes to earlier-begun chains, but never to a finding whose
head equals the judging review's own marker head (#437 round 3 F5, commit e31e795d, j262). Otherwise Claude's
"F1 fixed" closed Codex's unseen F1 and left the old chain's open. A new routing rule here needs both post
orders tested (tests/test_arm_cli.py gate 4c block), since the order decides which chain is "earlier". See [[arm-import-closure-needs-boundary-hunk]].

*References: arm-import-closure-needs-boundary-hunk*

*Anchors: `tools/fabric/github/arm_findings.py::f.head != marker.head`*

*Observed 2026-10-31 (devex-tooling)*
