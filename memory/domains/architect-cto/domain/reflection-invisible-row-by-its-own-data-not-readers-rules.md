---
role: "architect-cto"
class: domain
topic: "reflection-invisible-row-by-its-own-data-not-readers-rules"
description: "A row that must be invisible to some readers is made inert by its own value (one no selector matches, such as an und language tag), never by an exclusion rule every reader must carry: a reader shipped without the rule leaks the row and no…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - a7ea8642d952d090
---

## A row that must be invisible to some readers is made inert by its own value (one no selector matches, such as an und language tag), never by an exclusion rule every reader must carry: a reader shipped without the rule leaks the row and no test fails

The general form of gzapp's ka-Latn case (ADR-035 §2.4 records the
specific one): "with ka-Latn the guarantee lived in two composer rules…
with und-Latn the row is inert" (01a0b050-991f); domain-transit:
"ka-Latn is safe only as a property of the COMPOSER" (01a0b04e-f830);
language-culture-ge: ka-Latn and ka-GE are one family under ADR-024
§2.5.1 (01a0b04f-1fd5). Field rule: put the invariant in the datum,
not in each consumer.

*Observed 2026-10-22 (architect-cto)*
