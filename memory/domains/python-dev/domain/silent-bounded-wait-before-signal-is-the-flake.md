---
role: "python-dev"
class: domain
topic: "silent-bounded-wait-before-signal-is-the-flake"
description: "a test loop `for _ in range(100): if ready: break; sleep` that falls through silently, then signals or asserts anyway, is the load flake; reproduce with taskset-pinned busy loops"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7a7ccb882b5fcedf
---

## a test loop `for _ in range(100): if ready: break; sleep` that falls through silently, then signals or asserts anyway, is the load flake; reproduce with taskset-pinned busy loops

A flake of shape "exit right, output empty" (tests/test_run.py group-HUP case, j53, PR 319, 2026-10-19) was the test signalling a run before its suites had started: a bounded poll that falls through without a word when its ceiling passes. Read the failure's own counters first (`started=0`), then reproduce: 60 `while True: pass` loops and the case pinned to one core with `taskset -c N` failed 12 of 12 where the host's own load (50-90 on 10 cores) failed 0 of 80. Fix the class: one helper that waits for the condition with a ceiling a loaded machine does not reach, looks at the process (an exited run is reported at once), ends it, reports the missed precondition once, and makes the caller skip the case. A precondition label is for preconditions: the observation after a signal is a plain poll. A helper's own cases swap the reporting function for a capture, because the real one counts a failure.

**Why:** three review rounds on #319 each found one more way the helper itself could lie (still signalling after a miss, a 120 s wait on an exited run, a pid probe after the reap, a positive control that did not assert the run was left alone).
**How to apply:** in a test that signals a process, wait for the state with the process handed to the wait; for a session leader kill the group by its id (`killpg(p.pid)`, no `getpgid` probe after a reap); plant one mutation per branch of the helper, including `end_run` called on success.

*Observed 2026-10-19 (python-dev)*
