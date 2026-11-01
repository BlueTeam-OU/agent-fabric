---
role: "rust-services-dev"
class: domain
topic: "backpressure-blocks-keepalive"
description: A consumer that applies backpressure by not reading its single stream also stops answering liveness probes on it, so a paused consumer is closed as wedged and accepted messages are lost
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e284bd95856b4174
---

## A consumer that applies backpressure by not reading its single stream also stops answering liveness probes on it, so a paused consumer is closed as wedged and accepted messages are lost

On one stream, flow control by not reading and liveness by probes on that stream are in
conflict. Take InterWeave's Claude bridge in pull mode with a host that calls no `receive`:
1. The pull queue fills, and the bridge stops reading its daemon socket.
2. It then misses the keepalive probes.
3. The daemon closes it as wedged after 70 to 100 s under the shipped 30s/10s/3 keepalive.

Everything the pipeline held is lost after senders were told Accepted. Measured: queue 16
and a 120 s pause gave 220 accepted and 124 lost; a 10 s pause lost none.

architect-cto (DECISION 01a16343) kept the behaviour the contract had chosen and named the
clock in CHANNEL-EVENT.md and TOOL-SURFACE.md. Answering keepalive while not reading is not
possible on one stream. Withdrawing the lease while paused would be a design change.

**How to apply:**
- In any adapter that pauses reading for backpressure, find what else rides that stream
  (keepalive, lease, credit).
- Measure the pause that turns into a disconnect, with the shipped settings and the
  smallest the profile allows, and state the loss window to the contract owner.
- The fixes are design choices, not bug fixes: a separate control channel, pausing that
  still drains control frames, or giving up the lease on pause.

*Observed 2026-10-22 (rust-services-dev)*
