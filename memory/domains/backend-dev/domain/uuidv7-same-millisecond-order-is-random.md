---
role: "backend-dev"
class: domain
topic: "uuidv7-same-millisecond-order-is-random"
description: Guid.CreateVersion7 has no counter inside a millisecond, so two ids minted in one ms sort by random bits; a test that ORDER BYs minted ids and asserts positions is a coin flip
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "backend-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 36b25916909ee477
---

## Guid.CreateVersion7 has no counter inside a millisecond, so two ids minted in one ms sort by random bits; a test that ORDER BYs minted ids and asserts positions is a coin flip

.NET's `Guid.CreateVersion7()` fills the 48-bit millisecond timestamp and
leaves the remaining bits random. It has no monotonic counter, so two ids
minted in the same millisecond come out in either order. Seen in 0024's
StopSnapAndBoardingSchemaTests on #1159: two rows were minted back to back,
the query sorted by `shadow_evaluation_id`, and the assertion expected the
first-minted row first. It failed about half the time, and was green in the
author's run. db-admin confirmed the cause and keyed the comparison by id
(05fc30952).

**How to apply:** never assert positions over rows ordered by ids minted in
one test step. Compare a dictionary keyed by id, order by a fixed business
key, or mint the ids with a fixed order. One green run does not prove that a
coin-flip test is fixed. The fix is a comparison that cannot depend on
order. Production ordering by UUIDv7 is fine only at millisecond grain. The
same family of failure: [[shared-db-test-order]].

*References: shared-db-test-order*

*Observed 2026-10-25 (backend-dev)*
