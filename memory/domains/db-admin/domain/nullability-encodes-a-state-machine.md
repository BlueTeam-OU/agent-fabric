---
role: "db-admin"
class: domain
topic: "nullability-encodes-a-state-machine"
description: "A nullable timestamp copied from a sibling table carries that table's state machine; if the copy's status CHECK has no state where the column is absent, the nullability is a bug."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 1abeb3ab391f95b3
---

## A nullable timestamp copied from a sibling table carries that table's state machine; if the copy's status CHECK has no state where the column is absent, the nullability is a bug.

When a new table is deliberately modelled on an existing one — "the
shapes mirror the ADR-061 merchant chain", 0037's own header — the
nullability of each timestamp comes across with the column, and
nullability is not a shape. It is a claim about the state machine: this
column is absent in at least one state the table admits.

`driver_applications.submitted_at` was NULL-able from 0037:64 because
`merchant_applications.submitted_at` is, and there it is right —
`merchant_applications.status` admits `draft` and `changes_requested`,
and `MerchantApplicationRepository.SubmitSql` is a separate act that
stamps the column onto a row that already existed. The driver chain
copied the shape without those states: its CHECK is
`submitted | under_review | approved | rejected`, so the row is
*created by* the submission and there is no state in which it exists
unstamped. The contract that reads it,
`contracts/driver/driver-application.schema.json`, listed
`submitted_at` in `required` with no null member — and the database
accepted a row that contract cannot describe. Closed by 0052
(`SET NOT NULL`, PR held behind 0051).

**The check that finds it, in one query.** For each nullable column,
name the state in the table's own `status` CHECK where it is absent. If
you cannot, the nullability was inherited, not decided. Two
corroborations were already sitting in the same migration file and
neither needed the application code: the immutable child of the same
chain, `driver_application_revisions.submitted_at` (0037:99), was
ALREADY `NOT NULL`; and `decided_at` on the same table is *correctly*
nullable, because `submitted` and `under_review` are exactly the states
where nothing has decided it.

**"The one writer always sets it" is the weaker argument** and it is
the one you will be handed. It is a fact about today's code, so it
expires when someone adds a writer; the state machine is a fact about
the table. Use the writer inventory as the read-back that the
tightening is safe (and count it properly — this table had three
writes in `src/`, not the two the report named), not as the reason.

**Tighten with no backfill when the writer's shape says no row can
violate it.** A NULL then means a writer the migration does not know
about — the thing to find, not to paper over — and the ALTER fails
loudly naming the column (`ERROR: column "..." contains null values`).
Filling it from `created_at` reads plausibly, because the one writer
sets both from a single captured `@Now`, and is an ADR-017 §2.2 role
substitution: a lifecycle timestamp written into an occurrence one,
asserting a submission nobody observed. Put the operator's pre-flight
`SELECT count(*) ... WHERE <col> IS NULL` in the header instead.

Related: [[migration-numbers-move-until-they-land]] (0052 is committed
unpushed behind an unlanded 0051), [[verify-the-mutation-fired]] (the
control: with 0052 removed, exactly the 6 of 8 tests that depend on it
failed).

*References: migration-numbers-move-until-they-land, verify-the-mutation-fired*

*Observed 2026-09-18 (db-admin)*
