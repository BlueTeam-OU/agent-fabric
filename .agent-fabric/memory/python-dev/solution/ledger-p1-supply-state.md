---
role: "python-dev"
class: solution
topic: "ledger-p1-supply-state"
description: "j112 review-economics P1 ledger supply: where it lives, the decisions, traps met (empty-body INFOs, unknown vs 0, windowed by_pr, stale-mutation hang)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1cafeb059dacc0e1
---

## j112 review-economics P1 ledger supply: where it lives, the decisions, traps met (empty-body INFOs, unknown vs 0, windowed by_pr, stale-mutation hang)

j112 delivered 2026-10-14: contributor branch `develop-qzapp/python-dev-01/for/user/p1-ledger-python` (8d105933) for fabric-coordinator to fold into feat/review-economics. Never a PR.

- `tools/fabric/ledger.py` owns the file (path by the hook's rule, locked append, v1 reader, dispatch-header shapes); `review_codex.py` writes the codex row from `review()` wrapper + `Observed`; `control/ops/usage.py` `ledger_tokens` gives by_purpose (windowed), by_pr / unknown_by_pr (unwindowed); `results.py` `review_cost`.
- Reached by `gzcoord-inbox --replay <seq>` (ids unknown to the relay window need the full UUID or seq; `--history` lists seqs).
- Two architect INFOs arrived with EMPTY bodies (compose skeleton sent unfilled). Mine too once: a python fill failed and `gzcoord-send` ran next. Run fill, `grep` a marker from the body, THEN send, as separate steps.

**Why:** review class found these in the first cut: one malformed ledger line (deep nesting, 10**400 count) failed the whole tokens section; null counts read as 0 (unknown must be counted apart); by_pr windowed by the period cut PRs reviewed before it.
**How to apply:** reader of untrusted JSONL: catch RecursionError, cap counts below 2**53, validate names printed to terminals, wrap the optional half so the old answer survives. A mutation that makes a loop unbounded hangs the test: give the mutation runner a short timeout, treat timeout as killed, and make sure its finally restores the file.
Also: `test_review_codex` had a flake (`good_line.replace(head[:1], ...)` hit "codex"); test_launch_cli fails rc=143 sometimes under suite load, passes alone.

j111 (the architect first request, onto devex-tooling's branch) was superseded by the re-target and dropped; `fabric-jobs deliver` only appends artifacts, so a wrong `reply:` artifact is removed by editing the own jobs.json (reply:<id> must be the id of the message you replied TO). Codex rows carry `:usage-unverified` in status_source until a signed-in holder pins a live turn.completed (9dc2bdfe).

*Anchors: `tools/fabric/ledger.py::dispatch_header`, `tools/fabric/control/ops/usage.py::ledger_tokens`, `tools/fabric/results.py::review_cost`*

*Observed 2026-10-14 (python-dev)*
