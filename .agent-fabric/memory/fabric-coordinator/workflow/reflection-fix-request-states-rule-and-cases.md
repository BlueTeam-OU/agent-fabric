---
role: "fabric-coordinator"
class: workflow
topic: "reflection-fix-request-states-rule-and-cases"
description: "Asking for a fix to a review finding, or contracting a rule over combined state, states the rule and enumerates its cases with a control each (empty, padded, over-long, non-numeric; every chain×head×engine cell) — one-instance fixes breed…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9d7f11d4332cbfe2
---

## Asking for a fix to a review finding, or contracting a rule over combined state, states the rule and enumerates its cases with a control each (empty, padded, over-long, non-numeric; every chain×head×engine cell) — one-instance fixes breed the next finding round after round

On three PRs that week, the fix for one finding produced the next one. A parsing fix left its docstring contradicting the code. A fix kept an unchanged docstring. A length cap wrongly lowered a zero-padded value. A fourth case was the arm gate's judgement routing, which took three rounds (F1, F5, F8), one cell each: a repeated label, another engine on the same head, the same chain. A reviewer's suggested one-liner for the last of those would have broken a case already handled.

**Why:** a finding names one instance, and my follow-up REQUEST passed the instance on. Every round is a full supply, re-review and arm cycle.
**How to apply:** when I relay a finding or write a contract, state the rule the finding violates. List every input class or state cell the rule covers, with a fixture and a control for each. Ask the supplier to re-read the whole docstring and usage text against the code. Related: [[checks-need-a-control]], [[fix-a-claim-everywhere-it-is-made]].

*References: checks-need-a-control, fix-a-claim-everywhere-it-is-made*

*Observed 2026-11-01 (fabric-coordinator)*
