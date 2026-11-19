---
role: "python-dev"
class: solution
topic: "j219-drill-judge-merged-534"
description: "relay-outage judge (parity.py) fixes in #534 — unknown vs no for a missing log, exercised needs an InterWeave copy inside the drill; F1 wording deferred"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0e44c7d0d492b40f
---

## relay-outage judge (parity.py) fixes in #534 — unknown vs no for a missing log, exercised needs an InterWeave copy inside the drill; F1 wording deferred

#534 (b4bf6b1c, merged 2026-11-09): `relay_outage` in tools/fabric/gzcoord/carrier/parity.py reads an ack as "no" only for an ok:false line on the pair or any earlier ack line of the account (proof the log was kept); else "unknown". `carrier_only` now needs the first InterWeave copy in `[drill start, end)`.

**Why:** gzcoord-acks.jsonl did not exist before e4424b06, so an empty log is silence, not refusal; a pair both carriers delivered after the relay returned was sent late and proves nothing.

**How to apply:** a judge fed by a log that was introduced later must tell "absent" from "kept and empty"; evidence of a log being kept is a line older than the event. Carried P3 F1: the reason text still says "so the sender sent it late" though no sender record is read; "arrived outside the drill" is the exact wording. Arming minimum here was 1 work commit, so no owner's word was needed (a `--defer` for the P3 sufficed). The suite's own expected-FAIL lines make `grep FAIL` useless; read the last line and the exit code.

*Anchors: `tools/fabric/gzcoord/carrier/parity.py::relay_outage`*

*Observed 2026-11-09 (python-dev)*
