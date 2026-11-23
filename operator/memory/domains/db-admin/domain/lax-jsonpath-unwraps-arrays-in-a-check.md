---
role: "db-admin"
class: domain
topic: "lax-jsonpath-unwraps-arrays-in-a-check"
description: "A jsonb \"every value is a string\" CHECK in lax jsonpath admits {\"k\": [\"x\"]}; use strict with silent => true"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 17e7d766bf034386
---

## A jsonb "every value is a string" CHECK in lax jsonpath admits {"k": ["x"]}; use strict with silent => true

`NOT jsonb_path_exists(d, '$.* ? (@.type() != "string")')` passes
`{"k": ["x"]}` on Postgres 18: lax mode (the default) auto-unwraps the
array value, so the filter sees the string "x". `strict $.*` closes it,
but strict RAISES on a non-object ("wildcard member accessor can only be
applied to an object"), so add `silent => true` and leave non-objects to
a separate `jsonb_typeof(d) = 'object'` CHECK; then the result does not
depend on CHECK name order ([[check-constraints-fire-in-name-order]]).

Found by a podman probe before the test existed, then pinned: the lax
mutation reds exactly the array case and nothing else. gzapp
`infra/db/migrations/0027_i18n_baselines.sql`, commit 6f38ef604
(2026-11-09).

Related: a stored jsonb is never the input's bytes (keys sorted, by
length first, no whitespace, last duplicate wins), so a "same content?"
check is `col = $x::jsonb`, never a text compare.

*References: check-constraints-fire-in-name-order*

*Observed 2026-11-09 (db-admin)*
