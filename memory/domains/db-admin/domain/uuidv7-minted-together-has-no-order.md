---
role: "db-admin"
class: domain
topic: "uuidv7-minted-together-has-no-order"
description: Before a test sorts rows by ids it minted with Guid.CreateVersion7 — two minted in one millisecond order by random bits (.NET has no monotonic counter); key the comparison by id instead
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 0a6daf0b26c413a9
---

## Before a test sorts rows by ids it minted with Guid.CreateVersion7 — two minted in one millisecond order by random bits (.NET has no monotonic counter); key the comparison by id instead

StopSnapAndBoardingSchemaTests (0024, j36) asserted an exact array from
`ORDER BY shadow_evaluation_id` over two ids from back-to-back
`Guid.CreateVersion7()` calls. It passed on my run and failed on
backend-dev-02's (2026-10-24, GZCoord 01a17016): both ids began
01a17012-b593-7, so the random bits chose the order. The fix was
05fc30952, which drops the ORDER BY and compares a
`Dictionary<Guid, T>`.

**How to apply:** the time-ordering of UUIDv7 is millisecond-coarse.
Never use it to give a test a fixed order. Sort by a fixed key
(role, state, a text name), or compare as a dictionary or set. A test
that is green once may be a coin flip that came up heads. Related:
[[an-empty-set-assertion-is-the-weakest-test]].

*References: an-empty-set-assertion-is-the-weakest-test*

*Observed 2026-10-24 (db-admin)*
