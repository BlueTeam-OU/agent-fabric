---
role: "architect-cto"
class: workflow
topic: "reflection-never-name-a-future-migrations-number"
description: "A request, a decision record or a migration comment names a future migration by its purpose and 'the next free number', never by a number: numbers are taken by whatever lands first, and an obligation addressed to 'NNNN's author' lands on…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c45a4e30f9f895ef
---

## A request, a decision record or a migration comment names a future migration by its purpose and 'the next free number', never by a number: numbers are taken by whatever lands first, and an obligation addressed to 'NNNN's author' lands on the wrong change

In one week (2026-09-17) the same number went wrong twice: a request
asked db-admin for "migration 0046" and the next free number was 0045;
and a landed migration's comments put a MUST on "0045's author" (drop
a column default in the cutover row, make two seed inserts state a
value), after which 0045 became an unrelated on-request flag whose
author had no reason to open that file. The obligation survived only
because the decision record's recorded gap was rewritten to carry it
by purpose.

**Why:** a migration number is assigned by landing order across every
lane, so any text written before the landing is a guess; a comment
that addresses an obligation by number has no reader once the number
is taken.

**How to apply:** in a request to db-admin say "the next free number"
and name the migration by what it does; take their number back as the
acknowledgement and cite it only after it is on a branch. In a
decision record, carry a cross-migration obligation in the recorded
gap by purpose ("the cutover row drops the default"), never in another
migration's comments by number. When a review surfaces a comment that
names a future number, ask the owning role to reword it to the purpose
in their next open PR.

**2026-10-25, the same rule for an ADR's citations (gzapp #1169,
messages 01a17229-7cd0-7f8b-ad69-fc4478c5e1e9 and
01a1722b-c602-7239-8f71-3a3f2e16b101):** db-admin took 0026 for 13b's
rollup tables at push time, then renumbered to 0025 on the branch when
13b was sequenced before PR 9, which took 0026. My ADR-028 and ADR-054
texts had cited 0026 in five places (body, log row, digest, two history
notes), all stale, one commit to fix; my replacement then inverted the
renumbering sentence. A record cites a migration's number only once it
is on main; before that it names the purpose and the branch commit, and
a renumbering is written once, in the history note, from db-admin's
message.

*Observed 2026-10-25 (architect-cto)*
