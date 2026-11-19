---
role: "fabric-coordinator"
class: workflow
topic: "adjudication-range-is-head-to-head"
description: "Briefing a finding-adjudication — range must be <head>..<head>, or fabric-pr arm ignores its Judgement lines"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 382a3b9f018a1878
---

## Briefing a finding-adjudication — range must be <head>..<head>, or fabric-pr arm ignores its Judgement lines

`fabric-pr arm` gate 4c (agent-fabric tools/fabric/github/arm_findings.py) applies a
review's `Judgement:` to findings raised on head H only when that review's base is H
(an H..H round). An adjudication briefed on the PR's full range (base..H) is read as
another engine's review of the range and its judgements close nothing. On
blueteam.ee #16 (2026-11-02) two adjudications on 61e5168..0acf9e6 left all seven
findings open; they were lifted with --defer citing reviews 5739969315/5740049096.

**Why:** the gate keeps a second engine's own F1 from being closed by a judgement
that never saw it; base == head is how it tells an adjudication apart.
**How to apply:** in a `mode: finding-adjudication` request, set
`range: <head>..<head>`. Follow-up for the brief tool: j558.

*Observed 2026-11-02 (fabric-coordinator)*
