---
role: "p2p-network-dev"
class: domain
topic: "a-socketed-pipeline-bound-includes-the-kernel-buffer"
description: "A queue bound that holds in-process does not hold across a pushed Unix/TCP socket: the effective bound is queue + lane + client buffer + the kernel send buffer, and the socket's share is BYTES (~280 small frames in a default AF_UNIX…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bb3721baab0f3f14
---

## A queue bound that holds in-process does not hold across a pushed Unix/TCP socket: the effective bound is queue + lane + client buffer + the kernel send buffer, and the socket's share is BYTES (~280 small frames in a default AF_UNIX buffer on Linux), so a test must assert received == accepted, not a multiple of the bound

InterWeave's local IPC (#154, 2026-09-30): an event queue bound of 2 and a
conformance cap of 4x the bound passed in-process and failed over the socket
— 48 runs at 24 in parallel, 37 failed "8 accepted with nothing drained".
The server's 20 ms pump moves events out of the session queue into the
writer, which passes them straight into the socket; the kernel holds what its
per-socket byte buffer allows — measured ~280 small event frames (278) in a
default AF_UNIX send buffer. For small frames that dwarfs any multiple of the
queue; for 64 KiB payloads it is a handful.

Resolution: name the socket in the contract's pipeline sentence; make the
test's cap bound-independent (4x the bound + a fixed 1024-frame socket
allowance) and assert that everything accepted is received — no hidden
mailbox — rather than an exact bound. Shrinking `SO_SNDBUF` is still bytes,
and pumping only into the client's room needs a flow-control frame the
protocol lacks.

Two neighbouring traps: a port method with no maximum (`events()`) cannot be
drained "only into room" — it needs `events(max)`; and with one stream and no
flow control, a response queued behind events a client never drains waits
until it drains them (documented, not fixed).

**How to apply:** when stating or testing a bound across a socket, count the
kernel buffer in bytes as a stage of the pipeline, and run the test under
parallel load before trusting it.

*Observed 2026-10-18 (p2p-network-dev)*
