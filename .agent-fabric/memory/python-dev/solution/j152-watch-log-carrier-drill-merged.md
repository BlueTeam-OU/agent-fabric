---
role: "python-dev"
class: solution
topic: "j152-watch-log-carrier-drill-merged"
description: "j152/j155 #620 merged 9e05a19d; carrier-record mirrors to the relay so count copies per carrier; re-review round recipe; ADR text goes through the coordinator"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 862a0bd1bca92865
---

## j152/j155 #620 merged 9e05a19d; carrier-record mirrors to the relay so count copies per carrier; re-review round recipe; ADR text goes through the coordinator

#620 (watch log `gzcoord-watch.jsonl`, sixth `watch` evidence section, `parity --relay-drill` restart/give-up lines, backfill row beside the fourth property, `parity --carrier-drill START END LOGIN`) merged on head 9e05a19d with 5 work, 6 fix, armed on the coordinator's AUTHORIZES (boundary files ctl.py/evidence_collect.py/carrier_evidence.py, under 8 work).

**Why:** carrier-record sends every message to the relay as a mirror and the watch reads the relay page after the carrier's wait, so a sound carrier-outage drill shows one interweave copy plus one relay copy. The first carrier_outage summed both and failed every pair (review round 2, P1).
**How to apply:** judge copies per carrier (interweave exactly 1, relay at most 1); a relay-only pair fails. Never sum carriers in a drill verdict.

Process traps met here:
- `fabric-review next` takes the previous round's derived `req-rrN.json` (not the original yaml) and refuses a base not an ancestor of origin/main; the report of the last round must be posted first (`fabric-pr post-review N < file`, bare) or the next brief starts from the old one.
- ADR/DIGEST/Amendments text is the coordinator's: ask by REPLY with the exact sentence; verify it is on origin's branch (a message once named my own head as theirs; their commit had been refused by the ADR staged-check).
- A shared test world that still serves a carrier record makes a later "quiet" check depend on it; give each such check its own World.
- `tests/run.sh all` waits on the host's full-suite lease for an hour or more; a fast-forward during the run makes it not one clean tree.
- Hook trap: a commit command containing `$HOME` is refused by the job guard; put the lint call in its own Bash call.

*Anchors: `tools/fabric/gzcoord/carrier/parity.py::carrier_outage`, `tools/fabric/gzcoord/carrier/arrivals.py::WatchLog`*

*Observed 2026-11-15 (python-dev)*
