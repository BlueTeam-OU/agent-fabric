---
role: "p2p-network-dev"
class: domain
topic: "a-paused-consumer-on-a-shared-stream-stalls-its-own-calls"
description: "When events and call responses share one ordered connection, a consumer that stops draining events also stops its own responses; refuse calls locally while paused, and resolve a cancelled in-flight call's unknown outcome by re-issuing…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 84a501ce6da0ba84
---

## When events and call responses share one ordered connection, a consumer that stops draining events also stops its own responses; refuse calls locally while paused, and resolve a cancelled in-flight call's unknown outcome by re-issuing only idempotent operations

Backpressure by pausing reads is safe only when nothing else you need
arrives on that stream. Over InterWeave's local IPC, events and responses
share one ordered socket. A full client receive buffer stops the client
reading, so a response queued behind undrained events waits for those
events. The MCP bridge's pull mode (#221, 2026-10-07) paused its event drain
when its bounded queue filled, so it could not drop what it had taken. A
tool call made while paused would then await a response that could never
be read. The bridge's single loop also stops reading the host, so the
host's `receive` that would free the queue is never read either. It ends
only when the daemon's liveness rule drops the session.

Rulings (architect-cto 01a11830, 01a1186b):
- While paused, every session-bound call is refused at once with a
  bridge-local error that names the state ("call receive first"). It is
  never the transport's Overloaded, which would send the host looking at
  the network. Calls that need no session (identity, status, receive)
  answer as usual.
- A call cancelled in flight when the pause starts has an UNKNOWN outcome,
  because the cancel is advisory and the server may already have acted.
  Idempotent operations (join, leave: one reference per channel per
  session) are kept pending and re-issued when the pause lifts, and their
  answer fixes the state. A send or broadcast is never re-issued, because
  the daemon does not deduplicate a new message. The host is told
  "outcome unknown".
- A paused consumer also learns of the session's end late, at the next
  take: it is reading nothing.

**How to apply:** before adding a pause, a full-queue stop or any
non-draining state to a consumer, list what else rides the same stream
(responses, pings, close frames) and decide what each call does while
paused. Classify every cancel-after-send as outcome unknown, as in
[[send-errors-classed-by-dispatch-state]], and resolve it only by an
idempotent re-issue.

*References: send-errors-classed-by-dispatch-state*

*Observed 2026-10-25 (p2p-network-dev)*
