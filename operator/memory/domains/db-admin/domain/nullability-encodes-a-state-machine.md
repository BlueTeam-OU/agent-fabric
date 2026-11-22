---
role: "db-admin"
class: domain
topic: "nullability-encodes-a-state-machine"
description: "A nullable timestamp copied from a sibling table carries that table's state machine; if the copy's status CHECK has no state where the column is absent, the nullability is a bug."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 1abeb3ab391f95b3
  - d8dba4e7d807dfe5
---

## Correction of the nullability-encodes-a-state-machine slice: its ADR numbers are gzapp's and its migration numbers are folded into gzapp's baseline; the lesson is unchanged.

When a new table is modelled on an existing one, each timestamp's nullability comes
across with the column. But nullability is not a shape; it is a claim about the state
machine: this column is absent in at least one state the table admits. Example: in
gzapp, `driver_applications` was modelled on the gzapp ADR-061 merchant chain.

**What happened in gzapp.** `driver_applications.submitted_at` was nullable because
`merchant_applications.submitted_at` is, and there that is right. The merchant status
admits `draft` and `changes_requested`, and its submit is a separate act that stamps an
existing row. The driver chain copied the shape without those states: its CHECK is
`submitted | under_review | approved | rejected`, so a row is created by the submission
and no state exists in which it is unstamped. The driver-application contract required
`submitted_at` with no null member, yet the database accepted a row the contract cannot
describe. A `SET NOT NULL` closed it. That migration, like the one that created the
table, is now folded into gzapp's `0001_baseline.sql` (fourth baseline reset); cite the
baseline, not the old numbers.

**The check that finds it.** For each nullable column, name the state in the table's
own `status` CHECK where the column is absent. If you cannot, the nullability was
inherited, not decided. Look for corroboration in the same schema: an immutable child
table that already makes the column `NOT NULL`, and a sibling column (`decided_at`)
that is correctly nullable in exactly the undecided states.

**"The one writer always sets it" is the weaker argument**, and it is the one you will
be handed. It is a fact about today's code and expires when someone adds a writer; the
state machine is a fact about the table. Use the writer inventory to read back that the
tightening is safe, and count the writers yourself. Do not use it as the reason.

**Tighten with no backfill when the writers' shape says no row can violate it.** A NULL
then means a writer you don't know about, which is the thing to find, not to paper
over. The ALTER fails loudly and names the column. Filling the column from `created_at`
looks plausible but substitutes one time role for another (gzapp ADR-017 §2.2): a
lifecycle timestamp written into an occurrence one, asserting a submission nobody
observed. Put the operator's pre-flight `SELECT count(*) … WHERE <col> IS NULL` in the
migration header instead.

Related: [[migration-numbers-move-until-they-land]], [[verify-the-mutation-fired]].

*References: migration-numbers-move-until-they-land, verify-the-mutation-fired*

*Observed 2026-10-10 (db-admin)*
