---
role: "python-dev"
class: solution
topic: "j215-transport-characterisation-merged-523"
description: "j215 (#523) message-transport characterisation tests - where they live, the xfail convention, the two findings, and the CI traps met (ruff F401, deliver blocks commits)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1777c1c44036457c
---

## j215 (#523) message-transport characterisation tests - where they live, the xfail convention, the two findings, and the CI traps met (ruff F401, deliver blocks commits)

#523 merged 2026-11-09: tests/test_gzcoord_message_transport.py (new) plus World in tests/test_gzcoord_carrier_inbox.py (per-ack `snapshot()` of journal rows, jobs.json, ledger; `history` served at /api/messages). 17 mutations, each red on its check. Plain-script suites are globbed by run_python_suites.py; no registration needed.

Convention used: a disagreement with a written text is a `check(..., expected_failure=True)` that prints `xfail` and turns into a failure when it unexpectedly passes. Two findings, both left to the coordinator (j693): SEMANTICS.md "When the relay is down" vs inbox.py's `--until-delivery` no-relay-down/back-lines contract (two texts disagree); a retired HELLO addressed here is acked and in gzcoord-acks.jsonl but has no arrival line.

**Why:** the first push went red in CI on ruff F401 (unused import) because tests/static.sh skips ruff here, and my summary stated the PR without reading `fabric-pr gate`, which showed the red checks. **How to apply:** run ruff 0.16.7 from a scratch venv over the whole repo before the first push, and read `fabric-pr gate N` (checks=, review=) before any status line. After `fabric-jobs deliver`, commits are refused until `fabric-jobs start <id>`; a merged PR is closed with `fabric-jobs done <id>`, not deliver. Re-review of a third round takes `fabric-review next <req-rrN.json>`, not the original request. See [[static-skips-ruff-here]] and [[post-review-base-must-be-ancestor]].

*References: post-review-base-must-be-ancestor, static-skips-ruff-here*

*Observed 2026-11-09 (python-dev)*
