---
role: "python-dev"
class: domain
topic: "bounded-subprocess-three-seams"
description: A subprocess with a timeout fails at three seams reviewers keep finding — TimeoutExpired uncaught at the entry, a kill that reaches only the wrapper, a bound printed from exc.timeout (3.12 reports the time left)
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6c8b691e4c2d9f7c
---

## A subprocess with a timeout fails at three seams reviewers keep finding — TimeoutExpired uncaught at the entry, a kill that reaches only the wrapper, a bound printed from exc.timeout (3.12 reports the time left)

Giving a subprocess a timeout is not finished until three seams are closed; blind reviews found each of them on separate ports (reflection pass 2026-W42, as observed 2026-10-01..04).

1. **TimeoutExpired reaches the entry uncaught.** Every caller of a bounded call (verify, host-check, an addressee check) maps it to its own explicit "unavailable / no answer" line and exit status, distinct from "absent" and from non-zero exit. A lookup that got no answer must never read as "not there".
2. **The kill reaches only the wrapper.** `subprocess.run(timeout=)` kills the direct child (sudo, hostexec, ssh). Run the child in its own session and signal the group: SIGTERM to the tree, SIGKILL after a grace period, then wait, bounded, until every pid found is gone or a zombie, and say which pids still run if the bound passes. A test that reads /proc right after SIGKILL is racy (failed 2 of 10 runs); the helper waits so the test does not poll.
3. **Print the bound you passed, never `exc.timeout`.** On Python 3.12 `TimeoutExpired.timeout` is what was left of the bound ("0.999994 s"); 3.13 and 3.14 give the bound. CI runs 3.12, so only CI sees it. Re-raise `TimeoutExpired(cmd, bound)` from the one wrapper, and run the suite on 3.12 as well as the pinned interpreter.

**How to apply:** when adding or porting a bounded subprocess, check all three before review; test the first with a stub that sleeps, the second with a TERM-ignoring wrapper whose child must be gone, the third by asserting the printed number equals the constant.

*Observed 2026-10-15 (python-dev)*
