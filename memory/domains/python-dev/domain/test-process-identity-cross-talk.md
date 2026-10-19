---
role: "python-dev"
class: domain
topic: "test-process-identity-cross-talk"
description: "a test that finds \"its\" processes by command line kills and counts another concurrent run's; identify by a per-run env token, prove with decoys"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric-fleet"
derived_from:
  - 253d0be7b25edd9f
---

## a test that finds "its" processes by command line kills and counts another concurrent run's; identify by a per-run env token, prove with decoys

A test that looks in /proc for its own leftover processes by command line (`sleep 37.456` in cmdline) and SIGKILLs what
matches is not hermetic: a second run of the same test on the same account — e.g. one inside `tests/run.sh python`
beside a loop of it — kills the other's processes and counts them as its own survivors. In agent-fabric's
tests/test_run.py this was the real cause of "flakes under load" that I first patched as timing (wider budgets, gating
on readiness): all three guesses were wrong and dropped (j49, 2026-10-15, head 1fb8c99b).

**Why:** load makes runs overlap, so cross-talk looks exactly like a timing flake, and a timing patch "passes" a
20-run loop by luck.

**How to apply:** give each test run a token in the environment every child inherits (env() sets it) and match the
token in /proc/<pid>/environ as well as the cmdline (another account's environ is unreadable, so never "ours"). Prove
it before fixing: run the test ALONE beside decoy processes the experiment owns, shaped like the test's — the old code
fails and kills the decoys; the fix passes and leaves them. Add a negative control (disable the code that ends the
processes: the scan must still see this run's own survivors). Before patching a flake, read the failing output for
what it rules out: an EMPTY stdout (no headers) rules out "a line was lost", and a stopwatch bound adds nothing when
a kept line already proves the behaviour. Related: [[codex-marker-and-run-py-lessons]].

*References: codex-marker-and-run-py-lessons*

*Observed 2026-10-15 (python-dev)*
