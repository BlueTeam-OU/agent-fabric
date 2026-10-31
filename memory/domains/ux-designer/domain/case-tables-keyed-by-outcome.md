---
role: "ux-designer"
class: domain
topic: "case-tables-keyed-by-outcome"
description: "A spec's case table is keyed by the outcome observed, one row each, and its catch-all is checked both ways: no combination unnamed, no case another section requires swallowed"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7269677403b10fd7
---

## A spec's case table is keyed by the outcome observed, one row each, and its catch-all is checked both ways: no combination unnamed, no case another section requires swallowed

Rows that pair a cause with an outcome ("Storage with no record",
"AlreadyProvisioned with another PeerId") leave the other pairings
unnamed, and a builder fills them in by guess. Key the table instead by
what the screen can observe (the read-back shows the expected value /
nothing / another value / the read itself failed), one row each, so the
cause stops mattering. Then check the catch-all in both directions:
- does any outcome fall in no row (a record that opens to another value);
- does "any other X" also take in cases that another section requires
  to behave differently (an exception for "any other continuation of a
  live screen" swallowed in-flow prompts that had to raise the prompt).
**Why:** InterWeave identity note (#303, 2026-10-19): language-culture-en
twice found outcomes no row named; #304 round 4 (2026-10-20) found an
ADR carve-out whose "any other" took in four required in-flow cases.
**How to apply:** before review, list every observable result as a row;
for each catch-all or exception, name the cases it covers and grep the
spec for any of them required elsewhere. Narrow an exception to the one
case it is for.
Related: [[refused-write-read-back]], [[wording-pass-keeps-conditions]], [[refused-action-and-refused-undo]]

*References: refused-action-and-refused-undo, refused-write-read-back, wording-pass-keeps-conditions*

*Observed 2026-10-22 (ux-designer)*
