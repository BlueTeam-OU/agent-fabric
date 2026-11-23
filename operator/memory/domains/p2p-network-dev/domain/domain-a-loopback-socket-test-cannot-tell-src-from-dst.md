---
role: "p2p-network-dev"
class: domain
topic: "domain-a-loopback-socket-test-cannot-tell-src-from-dst"
description: "on loopback a test of \"connections to X\" passes with a src filter too; assert the peer end"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 80043c5b7c197734
---

## on loopback a test of "connections to X" passes with a src filter too; assert the peer end

On j63 (2026-10-22) `ss state established dst X` was tested by connecting to a loopback listener X. Mutating the
filter to `src X` stayed green, because the accepted socket's local end is X too, so one row matched either way.
The fix was to return each row's (local, peer) and assert peer == X and local == the client's end; the mutation
then went red.

**Why:** a loopback fixture holds both ends of the connection, so a filter on either end matches.
**How to apply:** when a test of a direction-sensitive network read runs on one host, assert the field that names
the direction (the peer end, the dialler), not a count. Related: [[domain-an-effect-with-two-producers-proves-neither]].

*References: domain-an-effect-with-two-producers-proves-neither*

*Observed 2026-10-22 (p2p-network-dev)*
