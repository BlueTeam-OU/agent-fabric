---
role: "db-admin"
class: index
description: "What db-admin knows and where it lives."
tier: 1
distilled_at: "2026-10-31"
---

# db-admin — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/db-admin/charter.md`](identities/roles/db-admin/charter.md) — The database as a system: schema, its changes, its performance, and how it behaves in containers on developer machines.

## brief

- [`identities/roles/db-admin/brief.md`](identities/roles/db-admin/brief.md) — How db-admin works day to day, in any project: the database as a system — migrations, the constraints that make a rule true, the index for a named query — settled by a probe, not an argument.

## domain

- [`memory/domains/db-admin/domain/a-backfill-into-a-waiting-state-retires-rows-past-the-event.md`](memory/domains/db-admin/domain/a-backfill-into-a-waiting-state-retires-rows-past-the-event.md) — Before a migration backfills rows into a waiting state whose only exit is a future writer event (await boarding, await approval), retire the rows that already passed that event; derive the list from every later state, not the spec's
- [`memory/domains/db-admin/domain/a-day-interval-is-not-24-hours.md`](memory/domains/db-admin/domain/a-day-interval-is-not-24-hours.md) — Before adding an hour-bound CHECK over timestamptz stamps, grep writers for 'N days' intervals — they are calendar arithmetic in the session TimeZone.
- [`memory/domains/db-admin/domain/a-value-set-assertion-needs-word-bounds.md`](memory/domains/db-admin/domain/a-value-set-assertion-needs-word-bounds.md) — Assert.Contains is a substring test, so a closed-set assertion can be satisfied by another member of the set; and \b is wrong for snake_case values.
- [`memory/domains/db-admin/domain/a-wrong-reason-in-a-comment-is-an-untested-axis.md`](memory/domains/db-admin/domain/a-wrong-reason-in-a-comment-is-an-untested-axis.md) — When a comment misstates WHY a check works, the clause it wrongly credits is usually the one nothing tests — treat it as a missing test, not a documentation defect.
- [`memory/domains/db-admin/domain/an-empty-set-assertion-is-the-weakest-test.md`](memory/domains/db-admin/domain/an-empty-set-assertion-is-the-weakest-test.md) — Assert.Empty on a query passes for ANY predicate matching nothing — including a malformed one; to test a predicate, give it something it must match and something it must not.
- [`memory/domains/db-admin/domain/an-fk-check-needs-a-full-index-on-the-referrer.md`](memory/domains/db-admin/domain/an-fk-check-needs-a-full-index-on-the-referrer.md) — A partial index on the referencing column (open rows only, live statuses only) leaves every parent DELETE's FK trigger a seq scan of the child — measured 47 s and 370 s for one sweep; size the referrer index for the delete, not the hot read
- [`memory/domains/db-admin/domain/an-implied-check-is-never-reported.md`](memory/domains/db-admin/domain/an-implied-check-is-never-reported.md) — A CHECK implied by others (x > 0 when 0 < y < x exists) can never be the constraint a refusal names — drop it, or its test asserts the wrong name.
- [`memory/domains/db-admin/domain/btrim-is-not-dotnet-trim.md`](memory/domains/db-admin/domain/btrim-is-not-dotnet-trim.md) — A blank or leading-digit test written in SQL and again in .NET disagrees on whitespace: btrim's default strips U+0020 only, Trim()/IsNullOrWhiteSpace strip 25 code points, [[:space:]] depends on the ctype.
- [`memory/domains/db-admin/domain/check-constraints-fire-in-name-order.md`](memory/domains/db-admin/domain/check-constraints-fire-in-name-order.md) — A test asserting WHICH CHECK refused a row must make the row violate only that one — Postgres evaluates a row's CHECKs alphabetically by name and reports the first.
- [`memory/domains/db-admin/domain/keycloak-db-migration.md`](memory/domains/db-admin/domain/keycloak-db-migration.md) — Keycloak self-migrates its backing database across intermediate minor versions on restart, unlike Postgres across majors
- [`memory/domains/db-admin/domain/latest-by-uuidv7-pk-walks-every-newer-row.md`](memory/domains/db-admin/domain/latest-by-uuidv7-pk-walks-every-newer-row.md) — WHERE key = @k ORDER BY <uuidv7 pk> DESC LIMIT 1 looks cheap in a probe and costs the whole table for an idle key; and an index on a column the hot UPDATE rewrites kills HOT
- [`memory/domains/db-admin/domain/nullability-encodes-a-state-machine.md`](memory/domains/db-admin/domain/nullability-encodes-a-state-machine.md) — A nullable timestamp copied from a sibling table carries that table's state machine; if the copy's status CHECK has no state where the column is absent, the nullability is a bug.
- [`memory/domains/db-admin/domain/pg-regex-s-admits-nbsp.md`](memory/domains/db-admin/domain/pg-regex-s-admits-nbsp.md) — Postgres 18's regex \S admits U+00A0 and follows the DB ctype; spell an ASCII range for a "no whitespace" CHECK
- [`memory/domains/db-admin/domain/pg18-not-null-is-a-pg-constraint-row.md`](memory/domains/db-admin/domain/pg18-not-null-is-a-pg-constraint-row.md) — Counting or listing a table's constraints from pg_constraint on Postgres 18 — NOT NULL is a row there too (contype 'n'), and LIKE's '_' is a wildcard; filter by contype and assert the exact set
- [`memory/domains/db-admin/domain/postgres-advisory-lock-respects-lock-timeout.md`](memory/domains/db-admin/domain/postgres-advisory-lock-respects-lock-timeout.md) — pg_advisory_xact_lock honors session lock_timeout and cancels with a normal error
- [`memory/domains/db-admin/domain/postgres-check-constraint-null-vacuous-pass.md`](memory/domains/db-admin/domain/postgres-check-constraint-null-vacuous-pass.md) — A Postgres CHECK constraint built from OR/equality over a nullable column passes vacuously when that column is NULL
- [`memory/domains/db-admin/domain/postgres-major-upgrade.md`](memory/domains/db-admin/domain/postgres-major-upgrade.md) — Postgres major-version bumps are pgdata-incompatible, and PG18+ additionally moved the data-directory mount point
- [`memory/domains/db-admin/domain/postgres-numrange-exclude-needs-numeric-cast.md`](memory/domains/db-admin/domain/postgres-numrange-exclude-needs-numeric-cast.md) — EXCLUDE USING gist with numrange() over double-precision columns fails unless both bounds are cast to numeric
- [`memory/domains/db-admin/domain/postgres18-skip-scan-changes-index-necessity.md`](memory/domains/db-admin/domain/postgres18-skip-scan-changes-index-necessity.md) — PostgreSQL 18 skip-scans a non-leading index column, so a predicate that needs an index on 16 may already be served on 18
- [`memory/domains/db-admin/domain/trailing-btree-keys-filter-without-heap.md`](memory/domains/db-admin/domain/trailing-btree-keys-filter-without-heap.md) — For an ORDER BY x LIMIT n poll with extra filters, put the filtered columns AFTER x in the btree — they are checked on the index entry, so skipped rows cost no heap visit (PG18).
- [`memory/domains/db-admin/domain/uuidv7-minted-together-has-no-order.md`](memory/domains/db-admin/domain/uuidv7-minted-together-has-no-order.md) — Before a test sorts rows by ids it minted with Guid.CreateVersion7 — two minted in one millisecond order by random bits (.NET has no monotonic counter); key the comparison by id instead
- [`memory/domains/db-admin/domain/widening-a-pairing-check-needs-the-old-rows-moved.md`](memory/domains/db-admin/domain/widening-a-pairing-check-needs-the-old-rows-moved.md) — Before re-adding an "all set or all NULL" CHECK with a new column, or a CHECK binding a state the old writer still writes — the old rows fail it; move them first with a TRUE value, and a control run on main tells whose reds remain
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## workflow

- [`.agent-fabric/memory/db-admin/workflow.md`](.agent-fabric/memory/db-admin/workflow.md) — A job delivered as a for/ branch or a memory stays "delivered" until closed with fabric-jobs done; check it when the caller's PR merges or the drain lands

## recall

- [`identities/roles/db-admin/recall.md`](identities/roles/db-admin/recall.md) — Where db-admin's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
