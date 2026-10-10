---
role: "p2p-network-dev"
class: domain
topic: "a-version-gate-has-two-sides"
description: "An additive-minor rule gates emission AND acceptance; put the version in the decoder's signature so no reader can skip it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - f00e4cb6217f6cee
---

## An additive-minor rule gates emission AND acceptance; put the version in the decoder's signature so no reader can skip it

LOCAL-IPC.md's additive-minor rule says a type is "emitted or accepted only
when the negotiated minor is at least the one that introduced it". #184 (IPC
2.1, `peer.path_changed`) gated only the server pump's emission; the client
decoded the 2.1 event on a 2.0 connection, and its scripted test granted
minor 0 and asserted acceptance — pinning the violation. Found by a bot
thread, judged real P3, fixed in 649665f8 by giving `Event::decode` /
`EventFrame::event` a required `IpcVersion` argument.

**Why:** a gate written at one end of a two-sided rule is the half-fix the
brief warns about; a test written from the emitter's belief agrees with it.

**How to apply:** for R2's `admin.trust.*` methods at minor 1 (and any
later minor), check both sides — the server refuses the method below 2.1
(`a_method_above_the_negotiated_minor_is_unsupported` exists for requests)
and the client never sends it below. Make the version a parameter of the
decode/encode function, not a check at one call site. Each side gets a
test at minor-below (refused) beside minor-own (accepted). Related:
[[stage-15-r1-r2-shapes]].

*References: stage-15-r1-r2-shapes*

*Observed 2026-10-04 (p2p-network-dev)*
