---
role: "ux-designer"
class: domain
topic: "thresholds-as-formulas"
description: "Write a compound threshold as an explicit formula (the larger of 40 % of the width and 96 dp) and give every 'that' its antecedent; a builder and a second-language reader both read a parenthesis two ways"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c46904842a90caa4
---

## Write a compound threshold as an explicit formula (the larger of 40 % of the width and 96 dp) and give every 'that' its antecedent; a builder and a second-language reader both read a parenthesis two ways

A gesture threshold written as "40 % of its width (at least 96 dp)"
reads as max(40 %, 96 dp) or as a claim that 40 % is always at least
96 dp. "A fling quicker than that springs back, which loses nothing"
left both "that" and "loses nothing" unresolved. Each cost a round trip
with language-culture before the builder could rely on it.

**How to apply:** in a spec, state each threshold with its operator in
words ("the larger of A and B", "within T of the first move, from
touch-down"), name the origin a distance counts from, and replace a
pronoun with its noun wherever a number follows. Say what "nothing
happens" means concretely (the row returns to rest, no action, the
person can try again).

Related: [[wording-pass-keeps-conditions]]

*References: wording-pass-keeps-conditions*

*Observed 2026-10-18 (ux-designer)*
