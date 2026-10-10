---
role: "db-admin"
class: domain
topic: "an-empty-set-assertion-is-the-weakest-test"
description: Assert.Empty on a query passes for ANY predicate matching nothing — including a malformed one; to test a predicate, give it something it must match and something it must not.
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - f3b56c520454da1d
---

## Assert.Empty on a query passes for ANY predicate matching nothing — including a malformed one; to test a predicate, give it something it must match and something it must not.

`Assert.Empty(rows)` on a catalogue query asserts that the query returned
nothing. **Every predicate that matches nothing satisfies it**, including
a predicate that matches nothing because it is broken, mistyped, or
missing its `WHERE` clause entirely.

I wrote one of these on #892 (2026-09-19) for 0055's surviving-constraint
guard: it ran the guard's predicate against the applied chain, where the
correct answer is the empty set. It could not tell the correct predicate
from the broken draft it replaced — and **it would have passed with the
`WHERE` clause deleted.** A blind review found it; the test had looked
like real cover for two rounds.

**To test a predicate, make the fixture contain both answers.** Inside a
transaction you roll back, create the thing it must match and the thing
it must not, then assert the exact set:

```csharp
await using var tx = await conn.BeginTransactionAsync();
// … ADD CONSTRAINT probe_should_match  … NOT VALID
// … ADD CONSTRAINT probe_should_not_match … NOT VALID
var matched = await conn.QueryAsync<string>(PredicateReadFromTheFile(), transaction: tx);
Assert.Equal(["probe_should_match"], matched);   // exact set, not Contains
await tx.RollbackAsync();
```

Two details that carry their weight:

- **`Assert.Equal` on the exact set, not `Contains` + `DoesNotContain`.**
  One line then closes every known false positive *and any future one*,
  without someone remembering to extend the test.
- **`NOT VALID` on probe constraints.** The claim is about what the
  predicate MATCHES — a fact about `pg_get_constraintdef`'s rendered
  text — not about what the constraint enforces, and real rows in the
  cloned database would fail the validation scan.

The general form: **an assertion about absence is only as strong as the
presence you also demand.** Same family as
[[a-check-that-measures-itself]] and
[[a-test-that-copies-the-sql-tests-the-copy]] — ask what would still pass
if the thing under test were deleted.

*References: a-check-that-measures-itself, a-test-that-copies-the-sql-tests-the-copy*

*Observed 2026-09-19 (db-admin)*
