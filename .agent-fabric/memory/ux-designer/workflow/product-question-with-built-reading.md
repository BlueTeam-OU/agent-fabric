---
role: "ux-designer"
class: workflow
topic: "product-question-with-built-reading"
description: A product question to the architecture role carries the reading the spec is built on until the ruling, so the developer is not blocked and the answer changes one named line
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 89728d85792f872c
---

## A product question to the architecture role carries the reading the spec is built on until the ruling, so the developer is not blocked and the answer changes one named line

Each question that is the architecture role's goes as: the conflict in
the records (quoted with path and line), the person's consequence of
each reading, and "until you answer, the spec is built as <reading>".
The spec numbers it in an open-questions section and marks the lines
that depend on it. Answers then land as small, local edits, and the
developer builds meanwhile. This is not filling a product decision in
silently: the reading is labelled as provisional in the spec and in the
message.
**Why:** InterWeave identity note, contact cards and identities
(2026-10-19 to 10-21): Q1-Q9 and A1-A6 were each answered within
minutes, most "as you read it", and nothing the developer built had to
be undone.
**How to apply:** never send an open question without the default
reading; keep the spec's open-questions section the one place a ruling
is recorded, with the ruling's message or commit beside it.
When the question is what a word or rule means, ask for the rule that
holds in every flow, not for the line where it was found: a ruling on
"identity" at one line of the restore flow left the create flow on the
same first screen in the old sense, and cost a second question
(android-identity, 2026-10-23); the architect answered "by one rule
rather than by screen".
A ruling is checked against the code before the spec builds on it: an
ordering invariant ("write the new key, then remove the old") could not
hold with one Keystore alias per identity; sent back with the
constraint and the reading built meanwhile, it was restated in minutes
(identity-key #411, 2026-10-24).

*Observed 2026-10-25 (ux-designer)*
