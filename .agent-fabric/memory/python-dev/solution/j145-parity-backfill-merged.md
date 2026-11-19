---
role: "python-dev"
class: solution
topic: "j145-parity-backfill-merged"
description: "j145 / PR 590 merged 791c4afc; parity report reads the relay backfill log; design decisions, review traps, suite and re-review recipe traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c8c453b69aa211f6
---

## j145 / PR 590 merged 791c4afc; parity report reads the relay backfill log; design decisions, review traps, suite and re-review recipe traps

PR #590 (j145) merged at 791c4afc on 2026-11-13: `interweave-evidence` takes a fifth section `backfills`
(rows {mid, outcome posted|present|over-age, at, delay_s, channel}), `evidence_collect.py` files
`<login>/backfills.jsonl` and meta `backfill_log`, `parity.py --relay-drill` gets a "relay record" per
carrier-alone pair and a fourth property.

Design that survived review:
- "none" is said only when a collected account whose deliveries name the MESSAGE-ID has its backfill log
  collected whole; a collection without the sender reads "not collected" (round-1 P2). Unknown stays unknown.
- A report-section stop marks `backfill_log` and `relay_outage` incomplete; a drill-section stop only
  `relay_outage`; a backfills stop only `backfill_log`. `skipped` takes max() over pages.
- A huge integer `delay_s` raises OverflowError in math.isfinite: catch it, skip and count.
- Fourth property: False on any over-age or none, else None if any pair is not collected, else True; the
  three older properties' `holds` is untouched.

**Why:** the 11-12 drill's collection (no file) must still compute.
**How to apply:** a later change to the drill report keeps the three-state property.

Traps met:
- `tests/run.sh` TaskStop leaves the child run holding the host slot: kill the python3 tests/run.py and
  run_python_suites.py pids by exact pid, or the next run waits for the lease. A loaded full run went red 9
  suites, each green alone; the coordinator accepted that with CI green on both Pythons.
- `fabric-review next REQUEST --pr N` wants the PREVIOUS round's range in the request (last head as end),
  after `fabric-review save N ROUND < report` of that round; edit out_of_scope/requirements in the derived
  req-rrN.json, render with `fabric-review brief`. Verdict-shaped requirement wording ("keeps", "fixed")
  refuses the render. A merge-of-main re-review is scoped by requirements (tree differs from main only in
  the PR's files).
- The coordinator merged main into my branch after its own ADR commit conflicted; arm then needs a review of
  that merge head, and the AUTHORIZES names the merge head. A P3 in the coordinator's text is deferred at
  arming (`--defer "<head8>:F<n>"`), not fixed, when a fix would move the authorized head.
- Open, not in this PR: F9 wording of docs/adr/history/ADR-029-amendments.md:419; the fetch-only drill risk
  (coordinator's j798); tests/test_control_carrier_evidence.py:1046 docstring wording.

*Anchors: `tools/fabric/gzcoord/carrier/parity.py::relay_record`, `tools/fabric/control/carrier_evidence.py::BACKFILL_OUTCOMES`, `tools/fabric/control/evidence_collect.py::backfill_log`*

*Observed 2026-11-13 (python-dev)*
