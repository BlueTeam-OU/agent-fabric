---
role: "architect-cto"
class: domain
topic: "a-notice-content-is-a-function-of-its-merge-key"
description: a pushed state notice merged by (id, evaluated_at) must have every member recorded by the evaluation that stamped it; a member computed at dispatch changes under the key
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 2290c4112f34404b
---

## a pushed state notice merged by (id, evaluated_at) must have every member recorded by the evaluation that stamped it; a member computed at dispatch changes under the key

A re-evaluable state notice that clients merge by `(id, evaluated_at)`
and keep the first copy of must carry only facts the evaluation that
stamped `evaluated_at` read and recorded. A member computed at dispatch
from a live row (ADR-078's "served" = last_contact_at > carried, read by
the push and the repair read while evaluated_at was the episode's open)
changes under a key the client already holds: the client never shows
it, or shows it at the wrong moment. The fix is to record the fact at
the evaluation (a column set with the episode's open), never to move
`evaluated_at` to "when the content last changed" (it is the
evaluation clock's stamp of an evaluation, ADR-017, not a content
version). Store the result as a boolean when the comparison was made on
one clock; a stored instant invites a later cross-clock comparison
(ADR-017 §5 rule 19).

**Why:** gzapp#1123 round-1 review, 2026-10-16; ADR-078 A 2026-10-16
(§2.3, §5 rule 10), supplied as 79e6791e4. Related: [[reference-instant-reads-the-bounds-clock]],
[[state-the-predicate-not-the-list-of-states]].

**How to apply:** when a record says "clients merge by (key, instant)",
check every member of the notice against the row the evaluation writes;
anything derived from a row that moves between evaluations is a
finding. Enumerations of that row's columns in the pillar ADRs
(ADR-054 §2.4.2, ADR-028 §2.1) change with it, each by its own triple.

*References: reference-instant-reads-the-bounds-clock, state-the-predicate-not-the-list-of-states*

*Observed 2026-10-15 (architect-cto)*
