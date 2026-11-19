---
role: "fabric-coordinator"
class: workflow
topic: "suite-verdict-only-at-exit"
description: "A suite log read before the background run exits shows sub-suite 'all ok' lines, not the run's verdict; I told the owner a run passed that had not finished (j750, 2026-11-11)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f8e5bc6a606c2662
---

## A suite log read before the background run exits shows sub-suite 'all ok' lines, not the run's verdict; I told the owner a run passed that had not finished (j750, 2026-11-11)

On 2026-11-11 (j750, BlueTeam-OU/agent-fabric#560) I tailed the log of a
`tests/run.sh` still running in the background, saw `all ok: 0 failed`,
and reported the suite as passed. That line is one sub-suite's verdict.
The run was still going after 48 minutes and held the full-suite lease,
so the next run I started sat waiting on it. By then the tree had also
changed under it (two merges and a fix), so its result meant nothing.

**Why:** the run's verdict is the last line `tests/run.sh` prints
(`all suites passed` or `N suite(s) FAILED`) and the exit code. Neither
exists until the background command's notification arrives.

**How to apply:**
- State a suite result only from the completion notification, the exit
  code and the final verdict line, never from a log read mid-run.
- Start the run on the final head, after every fold. A run whose tree
  moves under it is void: stop it (TaskStop, then check `ps` for an
  orphaned run.py, [[taskstop-leaves-suite-running]]) and restart.
- A local red confined to `== corpus lint` on sibling checkouts while
  CI's guards-and-suites is green is the known local drift
  ([[local-corpus-lint-red-interweave-index]]); say so in the arming
  basis rather than calling the suite green.

*References: local-corpus-lint-red-interweave-index, taskstop-leaves-suite-running*

*Anchors: `tests/run.py::suite(s) FAILED`*

*Observed 2026-11-11 (fabric-coordinator)*
