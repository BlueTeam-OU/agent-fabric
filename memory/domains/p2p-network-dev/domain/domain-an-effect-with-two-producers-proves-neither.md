---
role: "p2p-network-dev"
class: domain
topic: "domain-an-effect-with-two-producers-proves-neither"
description: a dial/connect observed end to end cannot prove one of two paths that both cause it; assert the store the path under test writes
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - b342cf1dcd4c14f9
---

## a dial/connect observed end to end cannot prove one of two paths that both cause it; assert the store the path under test writes

When two mechanisms each cause the observable effect (a connection to the peer), a test of that effect passes with
either one broken. On j62 (2026-10-22), `a_later_line_of_an_added_list_is_dialled` stayed green with the operator-door
loop mutated to `.take(1)`, because the running static-bootstrap provider dials the same overlay line. The fix was to
assert the door itself (`ComposedRuntime::operator_holds`, test-hooks) for every added line; that went red under the
mutation.

**Why:** a mutation check is what showed it. Reading the test said "every line is dialled", and that claim was true for
a reason other than the code under test.
**How to apply:** before trusting an end-to-end effect as evidence for path X, list every producer of that effect. If
there is more than one, assert X's own store or state, and keep the end-to-end case as the wiring check only. Mutate X
to confirm.

*Observed 2026-10-22 (p2p-network-dev)*
