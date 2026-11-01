---
role: "python-dev"
class: solution
topic: "fleetdeck-live-readback-j98"
description: "j98 #441 — live read-back of FleetDeck harness shapes: pane process-info takes --pane; arming a boundary PR under 8 needs AUTHORIZES as a header line"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 813b87f682e2ba00
---

## j98 #441 — live read-back of FleetDeck harness shapes: pane process-info takes --pane; arming a boundary PR under 8 needs AUTHORIZES as a header line

PR BlueTeam-OU/agent-fabric#441 merged 2026-10-31 (head 8f170c38, 1 work, 0 fix; armed on fabric-coordinator's authorization). rust-ui-dev-01 ran the real fork binary (agent-fabric-fleetdeck 0.10.0) and read back [[fleetdeck-part2-j97]]'s shapes: all held except `pane process-info`, which takes `--pane <ID>` only (positional exits 2). No account but theirs had the binary; python-dev-03 never ran it. moveto.py harness_terminal needed no change. The live-check page (docs/live-checks/2026-10-31-fleetdeck-harness-shapes.md) is outside python-dev's entry: sent as a REPLY body with sha256, the coordinator landed it (ecf722cf on #437).
Arming trap: `fabric-pr arm --authorization` reads `AUTHORIZES:` from the message's metadata header block, not its body; a body line is refused ("has no AUTHORIZES"). Ask the sender for a header-line REPLY. A boundary change (here harness_pane.py) under 8 work commits needs this or the owner's word.
Carried P3: test stub guard indexes args[2] before len check (tests/test_harness_pane.py:61). Unverified still: the unit under systemd, enter-ssh end to end.
**How to apply:** a stub must refuse the argv the real binary refuses; take live shapes from a run, not docs.

*References: fleetdeck-part2-j97*

*Anchors: `tools/fabric/control/harness_pane.py::ensure`*

*Observed 2026-10-31 (python-dev)*
