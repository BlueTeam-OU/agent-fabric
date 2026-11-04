---
role: "web-dev"
class: domain
topic: "joined-localized-strings-are-a-key"
description: "When a component would join two localized values (a label plus a summary, even screen-reader-only text): the join is a key with placeholders, not component punctuation"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 08156e5b3a553c1e
---

## When a component would join two localized values (a label plus a summary, even screen-reader-only text): the join is a key with placeholders, not component punctuation

Putting two dictionary values side by side in a component, for example
a cluster name before a status sentence as an accessible name, makes a
sentence no translator wrote. Screen readers run the two together, and
the separator, order and spacing differ by locale. Two locale owners
flagged the same run-on independently.

**How to apply:** make the combined phrase its own key with named
placeholders (`{cluster}`, `{summary}`), filled from the existing keys,
and ask each locale's owner for its value. Do not add a space, comma or
period in code. This applies to `sr-only` text and `aria-label` as much
as to visible copy.

Sources (GZCoord): 01a12515-41a3-70f7-84bd-a5814784902d,
01a12516-1830-7c93-a57a-99bf94a97a19, 01a12518-1085-77c5-875a-7f51bb474577.

*Observed 2026-10-24 (web-dev)*
