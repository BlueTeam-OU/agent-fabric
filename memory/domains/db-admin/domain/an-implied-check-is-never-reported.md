---
role: "db-admin"
class: domain
topic: "an-implied-check-is-never-reported"
description: "A CHECK implied by others (x > 0 when 0 < y < x exists) can never be the constraint a refusal names — drop it, or its test asserts the wrong name."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 3e98d6260c8664bb
---

## A CHECK implied by others (x > 0 when 0 < y < x exists) can never be the constraint a refusal names — drop it, or its test asserts the wrong name.

On 0014 (journey_reachability_policies, branch develop-qzapp/db-admin/feat/journey-call-sign,
2026-10-15) silent_after_wake_s > 0 was implied by granularity > 0 AND granularity < silent.
Every row violating it also violates the table-level `..._granularity_within_window`, which
sorts first by name, so the positive CHECK was never reported and its test expected a name
Postgres never returns.

**Why:** CHECKs fire in name order (see [[check-constraints-fire-in-name-order]]); an implied
constraint is dead weight with an untestable name.

**How to apply:** before writing a per-column bound beside a cross-column CHECK, ask whether
the pair already implies it; if so drop it and say in the header that the pair bounds it.

*References: check-constraints-fire-in-name-order*

*Observed 2026-10-15 (db-admin)*
