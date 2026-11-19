---
role: "fabric-coordinator"
class: workflow
topic: "drill-parity-collect-late"
description: "A drill's parity collected right after it reads UNSETTLED for copies that arrive later; collect with --until days after, keep the parity window as the drill's"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5bfcdb702259e3cd
---

## A drill's parity collected right after it reads UNSETTLED for copies that arrive later; collect with --until days after, keep the parity window as the drill's

The 2026-11-12 relay-outage drill was first collected at 10:54Z, the end of the window, and read UNSETTLED: the relay copy of 01a1cf4c arrived at 11:58:58Z after a resend by hand. A second collection on 2026-11-14 (`interweave-evidence --since <window-1h> --until <now>`, the same `parity --window/--drill/--relay-drill`) settled it: the three properties hold.

**Why:** parity takes arrivals only 60 minutes past each edge of the window. A copy that comes later shows as a miss.
**How to apply:** collect a drill's evidence with `--until` well after the drill (a day or more), and keep `--window` as the drill's own. Every relay copy is logged `unauthenticated` by design (carrier/adapter.py relay_arrivals, ADR-033 §6), so that verdict is not a fault. The fourth property (backfill) fails by age for a drill run before the backfill was deployed. Record: docs/live-checks/2026-11-12-interweave-drills.md (#612).

*Anchors: `tools/fabric/gzcoord/carrier/adapter.py::relay_arrivals`, `docs/live-checks/2026-11-12-interweave-drills.md`*

*Observed 2026-11-14 (fabric-coordinator)*
