---
role: "p2p-network-dev"
class: domain
topic: "domain-a-removal-test-must-read-what-it-removes-from"
description: "A \"removed X is used no more\" test passes for free unless the path it observes actually reads the store X was removed from; mutate the removal and watch it fail"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 2d269502d448735e
---

## A "removed X is used no more" test passes for free unless the path it observes actually reads the store X was removed from; mutate the removal and watch it fail

j54 (2026-10-22): the first test of "a removed bootstrap address is dialled
no more" closed the connection through a trust reset and waited for no
reconnect. It passed with the removal BROKEN (the address handed to the book
uncanonicalised, `/p2p/<peer>` suffix kept, so the book entry was never
found): the trust reset itself clears the peer's book, and the reconnect
after a graceful close comes from the discovery round, not the book. The book
is read only by `DialPeer` (an application send to an unconnected peer) and
the retry scheduler after a FAILED dial.

The bug was caught by the runtime crate's route-table guard
(`no_new_route_here_reaches_learn_address_unseen` counts `hand_over(`
callers), not by the behaviour test. Fixed by `forget_route` in
`crates/transport/libp2p/src/runtime/dialing.rs` (canonicalises like
`learn_route`), and the composition test now restarts the far end at the same
address and issues a direct send, which fails with the raw removal put back.

Rule: for every "no longer used" claim, name which reader consults the store,
make the test drive THAT reader, and mutate the removal to see it fail.
Feed the removal what the caller holds (the typed, suffixed address).

*Observed 2026-10-22 (p2p-network-dev)*
