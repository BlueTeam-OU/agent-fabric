---
role: "p2p-network-dev"
class: domain
topic: "a-wake-needs-a-per-entry-offer-mark"
description: "Waking a tick scheduler at the earliest due item - \"not yet offered\" must be a per-entry mark behind one setter, and the budget must stay per tick"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - ffcc92ea23087593
---

## Waking a tick scheduler at the earliest due item - "not yet offered" must be a per-entry mark behind one setter, and the budget must stay per tick

Adding a wake at the earliest due retry beside a periodic tick (InterWeave #674, ADR-0011 A 2026-11-14) took three review findings to get right:
1. `due > now` drops a retry that fell due while the loop turned on another arm: it waits a whole tick.
2. `due > last_offer_ms` (a timestamp) drops a retry made due in the same millisecond as an offer (learn_address, network_added, relay_reached all set due=now).
3. Each wake spending a fresh `max_retries_per_tick` turned the burst bound into none: retries due a ms apart each got their own budget.
What held: a per-entry `offered` bit set by take_due_retries on every due entry (leftovers included) and cleared only by the single setter of due_at_ms (`Retry::set_due`, which clears only when the value changes); one budget per tick period spent by wakes and tick, no wake armed while it is spent; a wake runs only the retries, not the tick's other work.
**Why:** leftovers must not re-arm the wake (spin), but nothing else may be left to the tick.
**How to apply:** for any "wake at earliest deadline + periodic sweep", enumerate every writer of the deadline and test a moved deadline on an already-offered entry (defer_retry_to_route_hold was the case a test missed until mutated).

*Observed 2026-11-15 (p2p-network-dev)*
