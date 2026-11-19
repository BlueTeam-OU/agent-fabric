---
role: "fabric-coordinator"
class: solution
topic: "no-module-named-lease-is-noise"
description: "a test_run failure detail showing \"no cpu slot (No module named lease)\" — not the cause"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2a3740c9f6bde0d8
---

## a test_run failure detail showing "no cpu slot (No module named lease)" — not the cause

In tests/test_run.py's python-section cases, stderr "no cpu slot (No module named lease)" is expected:
tree() copies tools/fabric/lease.py only with lease=True, and run.py's take_cpu_slot then runs on without a
slot by design. It shows up only because a failing case prints stderr. The real j863 red (debian, CI run
43417991778) was exit 130 with an empty stdout; python-dev-02 found 0/100 repros (j149). Since 9eeb8cad
(PR #612) run.py says on stderr when it KILLs the python runner after KILL_WAIT_S, and the group-signal
case's detail carries the seconds to the exit — read those on the next recurrence before diagnosing.

*Anchors: `tests/run.py::take_cpu_slot`, `tests/run.py::KILLing it`, `tests/test_run.py::def tree`*

*Observed 2026-11-14 (fabric-coordinator)*
