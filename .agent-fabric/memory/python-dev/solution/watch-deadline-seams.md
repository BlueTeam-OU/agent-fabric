---
role: "python-dev"
class: solution
topic: "watch-deadline-seams"
description: "gzcoord-inbox --deadline (j120, #285): a deadline checked only between arms is overrun by a hung relay; lock mark, flag-before-lock, worktree-name test failures"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9a93ea762bc08986
---

## gzcoord-inbox --deadline (j120, #285): a deadline checked only between arms is overrun by a hung relay; lock mark, flag-before-lock, worktree-name test failures

`gzcoord-inbox --until-delivery --deadline S` (default 6900) merged in #285 (tools/fabric/gzcoord/inbox.py, inbox_parts/watch.py, watchlock.py, cases in tests/test_gzcoord_port.py).

- A deadline checked only at the top of the outer loop is overrun by a relay that accepts and never answers: each slice's request timeout is slice + API_TIMEOUT (300 s). The slice's join loop in `wait_loop` must abandon at the deadline, as it does for a hold. Test with a raw accepting socket, not the stub.
- The flock is the stale-owner mechanism (the kernel frees it on any kill); the pid line in the file only says who held it. `release()` truncates it, so a pid found at the next start means the watch was killed and the start says so. Without the truncate the line fires on every start.
- A flag validated in `main()` runs after `run()` took the lock: it rewrites the mark and a second watch answers "do not run it again". Validate in `run()` before `take_or_report`.
- A mutation that removes a deadline check makes a loop test hang the suite: bound the test's own loop (raise Failed after N naps).
- Open at merge: the ALREADY_RUNNING text omits the deadline end (contract text, coordinator's); the relay-refused retry sleep is not capped to the deadline (about 30 s late).
- A worktree directory named agent-fabric-<topic> beside the main clone made test_arm_policy fail 50 cases there while the same commit passed in a scratch checkout; test_launch_cli group 6 failed only inside the full run. Run the suite from a scratch checkout of the head and compare with origin/main before calling a red yours.

*Anchors: `tools/fabric/gzcoord/inbox.py::deadline_arg`, `tools/fabric/gzcoord/inbox_parts/watch.py::out_of_time`, `tools/fabric/gzcoord/inbox_parts/watchlock.py::took_over`*

*Observed 2026-10-16 (python-dev)*
