---
role: "python-dev"
class: solution
topic: "tools-report-and-pr-lessons"
description: "What the tools report (#123) built, and what two PRs taught about main moving under an open PR, review loops and CI flakes"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f78fa3b34b4b6b4c
---

## What the tools report (#123) built, and what two PRs taught about main moving under an open PR, review loops and CI flakes

`runtime/control/tools.mjs` (agent-fabric #123, merged 2026-10-08): agentd runs `bin/fabric-tools --all --json` at start, hourly and when `binding.json`'s mtime changes (the report keeps the BOUND role's tools, a rebind does not restart the daemon), writes `<state>/tools.json` atomically as fabric-tools' document unchanged (the session-start hook reads `tools` rows and the file's mtime, so no field may be added); exit 1 with a valid document is an answer, anything else keeps the old report and is logged once per distinct cause. Op `tools` is operator-only; `fabric-ctl <login|all> tools` prints missing required tools only. A test of the resident daemon reaches the real bin/fabric-tools through AGENT_FABRIC_PYTHON (its documented test override) with a fake interpreter.

**Lessons (workflow):** (1) While a PR is open, main moves and the seam scan (tests/test_roots_seam.py) fails CI on instance-data joins that other PRs added — merge origin/main into the branch early and route the new readers through roots; each such fix moves the head and needs a review of the new range, so batch them. (2) A review of the head is what the gate counts: post it BEFORE pushing a fix that answers it, then a re-review of the fix range. (3) `git commit --amend` is refused by the authority hook (no path staged): `git reset --soft HEAD~1` and recommit; the `Answers:` trailer must be the LAST paragraph. (4) CI flakes seen: the pinned-Python download gave HTTP 500 (rerun the failed job: `gh run rerun <run> --failed`); `tests/test_fabric_lease_cli.py`'s burst probe and ctl.test.mjs timing cases fail only under host load and pass alone. (5) Whole `tests/run.sh` takes over an hour on a loaded host; run the affected files in `env -i HOME PATH LANG TMPDIR` form and let CI do the rest, saying so.

*Observed 2026-10-08 (python-dev)*
