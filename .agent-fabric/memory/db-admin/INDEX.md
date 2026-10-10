---
role: "db-admin"
class: index
description: "What db-admin knows and where it lives."
tier: 1
distilled_at: "2026-10-10"
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

- [`memory/domains/db-admin/domain/a-value-set-assertion-needs-word-bounds.md`](memory/domains/db-admin/domain/a-value-set-assertion-needs-word-bounds.md) — Assert.Contains is a substring test, so a closed-set assertion can be satisfied by another member of the set; and \b is wrong for snake_case values.
- [`memory/domains/db-admin/domain/a-wrong-reason-in-a-comment-is-an-untested-axis.md`](memory/domains/db-admin/domain/a-wrong-reason-in-a-comment-is-an-untested-axis.md) — When a comment misstates WHY a check works, the clause it wrongly credits is usually the one nothing tests — treat it as a missing test, not a documentation defect.
- [`memory/domains/db-admin/domain/an-empty-set-assertion-is-the-weakest-test.md`](memory/domains/db-admin/domain/an-empty-set-assertion-is-the-weakest-test.md) — Assert.Empty on a query passes for ANY predicate matching nothing — including a malformed one; to test a predicate, give it something it must match and something it must not.
- [`memory/domains/db-admin/domain/keycloak-db-migration.md`](memory/domains/db-admin/domain/keycloak-db-migration.md) — Keycloak self-migrates its backing database across intermediate minor versions on restart, unlike Postgres across majors
- [`memory/domains/db-admin/domain/nullability-encodes-a-state-machine.md`](memory/domains/db-admin/domain/nullability-encodes-a-state-machine.md) — A nullable timestamp copied from a sibling table carries that table's state machine; if the copy's status CHECK has no state where the column is absent, the nullability is a bug.
- [`memory/domains/db-admin/domain/postgres-advisory-lock-respects-lock-timeout.md`](memory/domains/db-admin/domain/postgres-advisory-lock-respects-lock-timeout.md) — pg_advisory_xact_lock honors session lock_timeout and cancels with a normal error
- [`memory/domains/db-admin/domain/postgres-check-constraint-null-vacuous-pass.md`](memory/domains/db-admin/domain/postgres-check-constraint-null-vacuous-pass.md) — A Postgres CHECK constraint built from OR/equality over a nullable column passes vacuously when that column is NULL
- [`memory/domains/db-admin/domain/postgres-major-upgrade.md`](memory/domains/db-admin/domain/postgres-major-upgrade.md) — Postgres major-version bumps are pgdata-incompatible, and PG18+ additionally moved the data-directory mount point
- [`memory/domains/db-admin/domain/postgres-numrange-exclude-needs-numeric-cast.md`](memory/domains/db-admin/domain/postgres-numrange-exclude-needs-numeric-cast.md) — EXCLUDE USING gist with numrange() over double-precision columns fails unless both bounds are cast to numeric
- [`memory/domains/db-admin/domain/postgres18-skip-scan-changes-index-necessity.md`](memory/domains/db-admin/domain/postgres18-skip-scan-changes-index-necessity.md) — PostgreSQL 18 skip-scans a non-leading index column, so a predicate that needs an index on 16 may already be served on 18
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## recall

- [`identities/roles/db-admin/recall.md`](identities/roles/db-admin/recall.md) — Where db-admin's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
