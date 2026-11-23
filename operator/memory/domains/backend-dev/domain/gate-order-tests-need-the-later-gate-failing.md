---
role: "backend-dev"
class: domain
topic: "gate-order-tests-need-the-later-gate-failing"
description: "a test that a gate refuses \"first\" must leave the LATER gate failing too; satisfying the later gate to test \"records nothing\" silently drops the order check"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "backend-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 47816b3c19bda94a
---

## a test that a gate refuses "first" must leave the LATER gate failing too; satisfying the later gate to test "records nothing" silently drops the order check

Two properties hide inside one refusal test of a chained gate (role → reason → step-up → write):
- **Order.** The earlier gate answers first. Testing this needs the later gate failing as well (no step-up), so a swap of the two checks answers the later gate's status instead.
- **Effect.** The refusal records or writes nothing. Testing this needs the later gate satisfied (stepped up), so the earlier gate is the only thing standing between the request and the write.

On gzapp #1237, fixing the second property (dfc0136dd moved the no-reason history request onto a stepped-up bearer) removed the first. The re-review caught it as F4: swapping RequireReason and the step-up check passed every test. The fix (73e7b2a94) sends the request both ways in one theory.

Also: a "records nothing" assertion that cannot key its lookup (a blank reason) counts the whole event kind before and after. That is safe only because AdminApiFixture clones one database per test class, which runs serially; see [[shared-db-test-order]].

**Why:** a mutation check of each property separately is what shows both are pinned.
**How to apply:** when writing or changing a gate test, mutate the order (swap the two checks) and the effect (move the check after the write). Both must fail. Related: [[widening-a-guard-leaves-its-recovery-branch]].

*References: shared-db-test-order, widening-a-guard-leaves-its-recovery-branch*

*Observed 2026-11-10 (backend-dev)*
