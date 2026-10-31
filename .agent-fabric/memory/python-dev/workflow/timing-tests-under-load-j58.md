---
role: "python-dev"
class: workflow
topic: "timing-tests-under-load-j58"
description: "j58 (#296) — how to bound a timing test: event or CPU time, ceiling an unbounded call would show; synthetic load recipe; traps"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 877f213f4862bc52
---

## j58 (#296) — how to bound a timing test: event or CPU time, ceiling an unbounded call would show; synthetic load recipe; traps

Timing tests (PR 296, 2026-10-18): measure from an event (fake gateway stamps the ask, fake harness stamps its end, launcher must end <5 s after) or in CPU time (`time.process_time`, least of nine) instead of wall time of a whole launch; a ceiling is what the unbounded defect shows, plus an additive allowance of ~1 s on a short bound, never a bare 10x (a deadline 4x late must still fail: plant the 4x timer).
**Why:** at load 60 the wall-clock linear-time case failed 103 of 150 tries, CPU time 0; the review found the 10 s trickle ceiling passed a 4x-late deadline.
**How to apply:** synthetic load = N `timeout S python3 -c 'while True: pass'` (3x cores); never `while pgrep -f "<that string>"` (matches its own shell and loops forever); a fake that makes a socket from an fd must keep the object (collected, it closes the fd); the launcher runs under `python -I`, so PYTHONPATH tricks do nothing; `git commit` signing can fail on the OTS calendars under load, and a retried `git add; git commit` chain may then commit both files in the second one. `fabric-pr arm --dry-run <n> --basis x` prints the minimum.

*Observed 2026-10-18 (python-dev)*
