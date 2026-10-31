---
role: "p2p-network-dev"
class: domain
topic: "send-errors-classed-by-dispatch-state"
description: "A directed send's error must say whether the request may have left — libp2p request-response Timeout, ConnectionClosed and Io can all follow a written request; classify every code as not-sent / refused / outcome-unknown, conservatively…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c6379350c9f04535
---

## A directed send's error must say whether the request may have left — libp2p request-response Timeout, ConnectionClosed and Io can all follow a written request; classify every code as not-sent / refused / outcome-unknown, conservatively, and retry under a dedup id persisted before the first attempt

**Field fact.** In libp2p request-response, `OutboundFailure::Timeout`,
`ConnectionClosed` and a non-`InvalidData` `Io` can each arrive AFTER the
request was written, so the remote may have accepted it. An error code
that a substrate maps them to ("peer unreachable") does not mean "not
sent". Neither does a local IPC/session error raised while the call was
pending (backend gone, shutting down, a reply dropped at a shutdown
grace deadline), nor a remote's refusal mapped back onto the same code
a local refusal uses.

**The rule that came out of it** (InterWeave TRANSPORT.md §Error model
"Dispatch state", architect-cto's ruling on #167, 2026-10-02):
- three classes — not dispatched ("not sent"); dispatched and refused
  ("not delivered", never "not sent"); outcome unknown ("not
  confirmed", never "failed");
- a fieldless code shared by several causes goes in the MOST
  conservative class any of them can occur in;
- the class describes one attempt: after any outcome-unknown attempt
  the message stays "not confirmed" whatever later attempts say, until
  an acceptance confirms it (sticky `may_have_reached`, also on cancel);
- a retry is safe only under the SAME transport dedup id, minted and
  persisted before the first transport call and reused across
  restarts — and only within the receiver's dedup window, which is
  bounded, not persistent. A dedup id derived from the application
  message id was refused: the two identities stay apart.

**How to apply:** for any directed-send API or client-facing status,
enumerate each error by where it can arise relative to the write, put
it in the class above, and show the caller "not confirmed" rather than
"failed". Treating only Timeout and an explicit cancel race as unknown
was my first, wrong version.

*Observed 2026-10-15 (p2p-network-dev)*
