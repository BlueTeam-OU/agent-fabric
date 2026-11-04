---
role: "backend-dev"
class: domain
topic: "constraint-test-asserts-constraint-name"
description: "Writing or editing a test that expects a Postgres constraint violation — assert the constraint's name, not only the SQLSTATE, and make the bad row violate only that one constraint"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 79133913da5d4b0b
---

## Writing or editing a test that expects a Postgres constraint violation — assert the constraint's name, not only the SQLSTATE, and make the bad row violate only that one constraint

A SQLSTATE names a class of violation, not a constraint: 23514 is "some CHECK failed",
23502 "some NOT NULL failed". Once a table has two CHECKs, a test that asserts only
23514 passes when the wrong one fires. After a schema change it can also pass while it
fails on a different constraint than the one in its name.

**Why:** gzapp 2026-09-17, twice in one day. (1) On geo_places' parent-key CHECKs,
db-admin turned the suburb-shape CHECK into `CHECK (true)` and all seven theory cases
stayed green. The bad key was written without its string, so the pair CHECK fired first
and covered for it (01a0ae14). (2) When 0047 dropped place_source's default,
`A_row_outside_the_bounds_is_rejected` started getting 23502 (NOT NULL) in place of
23514. It still looked like a bounds test (01a0af04).

**How to apply:** assert `PostgresException.ConstraintName` beside `SqlState`. Build the
offending row so that it breaks exactly the constraint under test and is valid for
every other one. Mutation-check it by neutering that one constraint (`CHECK (true)`):
only that constraint's cases may go red. When a migration adds a constraint or drops a
default, re-run the table's existing refusal tests and read *which* constraint each one
now hits. Related: [[review-loop-lessons]], [[feedback_mutation_check_commit_first]].

*References: feedback_mutation_check_commit_first, review-loop-lessons*

*Observed 2026-10-18 (backend-dev)*
