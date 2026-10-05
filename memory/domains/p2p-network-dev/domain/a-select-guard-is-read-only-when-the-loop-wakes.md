---
role: "p2p-network-dev"
class: domain
topic: "a-select-guard-is-read-only-when-the-loop-wakes"
description: "A tokio::select! branch guard (`if lane.capacity() > 0`) is evaluated only when the loop wakes; waiting on another task to free room stalls forever on a connection with no timer. #151 had it twice"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - d0d66e575023bdf4
---

## A tokio::select! branch guard (`if lane.capacity() > 0`) is evaluated only when the loop wakes; waiting on another task to free room stalls forever on a connection with no timer. #151 had it twice

In #151 (InterWeave ipc-server, 2026-09-30) two select arms were guarded on an mpsc lane's free room:
the event pump (`poll.tick(), if pumps_events && events.capacity() > 0`) and the reader
(`reading = outbox.is_empty() && control.capacity() > 0`). A guard is read once per loop iteration;
when every enabled branch is pending, the writer task draining the lane does NOT wake the select, so
the guard stays false. Events stopped until a keepalive; quiet admin/diagnostics connections hung at
exactly CONTROL_LANE (67) answers. Tests missed both because every test connection had a 20 ms tick
(the `events` capability) that woke the loop and masked it.

**Why:** the fix for the first instance (3d614cda) was not applied to its twin in the same file; the
next review round found it (3fb13457).

**How to apply:** never guard a select arm on room another task frees. Make the room a WAKE instead
(`reserve_owned()` / `reserve()` as its own arm, or `Sender::closed()` for a dead receiver), or read
the room inside the arm body on a timer that always runs. When fixing one guard, grep every
`select!` in the crate for `capacity()` / `is_empty()` guards in the same pass, and run the
backpressure tests over a connection with NO timer of its own (no keepalive, no event tick).

*Observed 2026-09-30 (p2p-network-dev)*
