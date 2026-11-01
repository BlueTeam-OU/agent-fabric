---
role: "p2p-network-dev"
class: domain
topic: "domain-a-past-time-converts-in-its-own-direction"
description: "monotonic→wall conversion written for deadlines (wall + (until-now) saturating) reads a past time as now; test that a later reading does not move it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - af1357b01818996c
---

## monotonic→wall conversion written for deadlines (wall + (until-now) saturating) reads a past time as now; test that a later reading does not move it

A runtime that keeps times on a monotonic clock and shows them on the wall clock
often converts with `wall + until.saturating_sub(now)`, which is right for a
deadline and silently wrong for a past instant: the subtraction saturates to 0
and every past time reads as "now". In InterWeave the peer-gate photograph's
`on_wall` (crates/transport/libp2p/src/runtime/mod.rs) did this; `last_seen_ms`
(peer-list 1.2.0, j88, commit 98ce1ceb) needed `wall - (now - at)`.

The first assertion (value inside the window the event happened in) PASSED with
the bug, because "now" at the reading was still inside it. What caught it was
reading again after a sleep and asserting the value did not move.

**How to apply:** for any recorded past instant, name the direction in the
conversion, and pair the "inside the window" assertion with "a later reading is
unchanged".

*Observed 2026-10-28 (p2p-network-dev)*
