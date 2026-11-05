---
role: "devex-tooling"
class: solution
topic: "arm-findings-same-head-engines"
description: arm_findings gate 4c — a judgement never closes a finding raised on its own head (either pool, own chain included) unless its base is that head (H..H)
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0fb52fc39cc03492
---

## arm_findings gate 4c — a judgement never closes a finding raised on its own head (either pool, own chain included) unless its base is that head (H..H)

In tools/fabric/github/arm_findings.py read(), chains join by base= matching an earlier head=, so two engines'
reviews of one range can start two chains (both on a base B that is no review head) or continue ONE chain (both
on a chain's head h0); either way each numbers its findings from F1. The rule as merged (ab871063, #437 round 4
F8; round 3 F5 was e31e795d): when a review's `Judgement: F<n>` is routed, findings whose head equals the
judging review's own marker head are filtered out of BOTH pools — its own chain and the earlier-begun chains —
unless the judging review's base equals its head (an H..H review, the next round or an adjudication, which has
read the findings raised on H). After that filter: its own chain whenever that chain ever raised the label (open
or closed), else only chains begun before it; newest first, a clearing verdict preferring an open finding. A
chain that raised the label only on this head therefore counts as never having raised it.

Why both pools: round 3's filter covered the earlier-chain pool only, so Claude's "F1 | fixed" on h0..H,
posted after Codex's in the same chain, closed Codex's F1 raised on H and armed with it unjudged. A new routing
rule here needs both post orders tested plus the H..H control (tests/test_arm_cli.py gate 4c block), since the
order decides which chain or finding is "earlier". See [[arm-import-closure-needs-boundary-hunk]].

*References: arm-import-closure-needs-boundary-hunk*

*Anchors: `tools/fabric/github/arm_findings.py::marker.base == marker.head`*

*Observed 2026-11-01 (devex-tooling)*
