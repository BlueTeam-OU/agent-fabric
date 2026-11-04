---
role: "rust-services-dev"
class: domain
topic: "loss-counter-at-the-drop-site"
description: Count dropped messages where the drop happens, never from the event the drop emits
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - deb8184dd418a9b4
---

## Count dropped messages where the drop happens, never from the event the drop emits

A loss counter derived from a "dropped" event undercounts under exactly the pressure it measures: an
event is pushed only while its outbox has room, so a burst that overflows the queue can overflow the
event channel too. Keep the counter (a monotonic u64) in the structure that drops, incremented on each
drop and refusal arm. Where the drop sits on a hot path built to bound per-message work (an ingress
rate gate), keep it O(1): count per channel, and have each consumer snapshot the value at join and fold
the difference in at leave and at read. Name what is not counted (drops before your code sees the message),
and say a zero means "none counted", not "none lost".

InterWeave case (2026-10-24): `BroadcastDropped` was outbox-bounded and the ingress refusal was not counted
at all; IPC 2.11 `session.losses` counts both at the drop sites, ruled by architect-cto's DECISION.

**How to apply:** when a service exposes loss, backpressure or refusal counts, check where each one is
incremented before trusting it. One read through an event or channel is already a finding.
Related: [[loss-counter-is-a-session-read]].

*References: loss-counter-is-a-session-read*

*Observed 2026-10-25 (rust-services-dev)*
