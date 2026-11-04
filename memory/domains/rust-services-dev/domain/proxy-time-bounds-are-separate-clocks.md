---
role: "rust-services-dev"
class: domain
topic: "proxy-time-bounds-are-separate-clocks"
description: "A streaming proxy's time bounds are three separate clocks (commit deadline, upstream idle, hard ceiling); what each one counts, and the race when a timeout fires"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 62ef64e717070450
---

## A streaming proxy's time bounds are three separate clocks (commit deadline, upstream idle, hard ceiling); what each one counts, and the race when a timeout fires

A streaming proxy bounds a request with separate clocks. Each has its own
owner and counts something different. Folding them into one timeout is
how a slow reader gets cut, or a silent upstream gets to hold a slot.

1. **Deadline to commitment.** Covers connect, the upstream head and the
   proxy's own body read. Its expiry is the proxy's own answer
   (408/504), written before anything has been forwarded.
2. **Idle limit.** Counts only upstream silence. A client that stops
   reading is not upstream silence: the server does not poll the body
   then, so the idle timer must not run while it is not polled.
3. **Hard ceiling.** Bounds whatever either peer does, including a
   client that stops reading. Only a connection-level timer can enforce
   that, because no timer inside the body runs while the body is not
   polled.

**The race.** When a timeout fires, its answer must still be writable. A
ceiling armed at arrival and equal to the deadline drops the 408/504
unwritten. So arm the ceiling when the answer is handed over, with a
short grace for writing a head. Never extend that grace to a committed
body.

Test it over real sockets: an upstream silent after its head, a stream
that never ends, a client that stops reading, and a timeout that fires
at the same moment as the ceiling.

Evidence, agent-fabric-gateway main: PRs #16 and #17 (the race was
reproduced in #16's review round 3); tests/anthropic-passthrough/tests/time_bounds.rs
`a_timeout_is_answered_when_the_ceiling_is_the_deadline`,
`a_client_that_stops_reading_is_held_to_a_lowered_ceiling`,
`an_upstream_silent_after_its_head_is_cut_at_the_idle_limit`, and the
same cases in openai-responses-passthrough streams.rs. The gateway's own
values and code paths are in [[gateway-time-bounds-design]] (solution).
Related: [[response-commitment-point]], [[hyper-cancellation-and-head-deadline]].

*References: gateway-time-bounds-design, hyper-cancellation-and-head-deadline, response-commitment-point*

*Observed 2026-10-18 (rust-services-dev)*
