---
role: "python-dev"
class: workflow
topic: "j126-cleanup-kill-guard-merged"
description: "j126 #518 merged f5c8ba23; a cleanup kill needs both the running() guard and ProcessLookupError tolerance; hook/brief traps"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 447b6680a204b86c
---

## j126 #518 merged f5c8ba23; a cleanup kill needs both the running() guard and ProcessLookupError tolerance; hook/brief traps

#518 merged (f5c8ba23): test_review_codex's cleanup kill of a probe's left-behind member goes through `reap()` (tolerates ProcessLookupError) and stays behind `if running(pid)`.

**Why:** my first edit replaced `if running(left): os.kill(...)` with a bare `reap(left)`, which signalled an already-reaped PID on every passing run; the blind review caught it (P2). Tolerating the error is not a licence to drop the guard that keeps the success path signal-free.

**How to apply:**
- A re-review request has no `previous_findings` field: the brief reads the last posted review; post the first review before rendering round 2.
- A command with `$HOME`/`$PWD`-style substitutions beside `git commit`/`fabric-pr` is refused by the job-copy guard; run tests and commits as separate calls.
- Arm minimum in agent-fabric is 1 work commit (`fabric-pr arm --dry-run --basis x` prints the rule); the gate counts the Answers: commit as fix.
- Red platform-smoke debian can be another suite's flake (test_review_mcp.py:430 empty pidfile, queued as j128): read the failed suite's block, `gh run rerun <id> --failed`, do not widen the PR.
- `fabric-jobs done` then needs `deliver` of the PR and a memory change before `switch`.

*Anchors: `tests/test_review_codex.py::def reap(pid)`*

*Observed 2026-11-09 (python-dev)*
