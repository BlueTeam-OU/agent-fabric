---
role: "fabric-coordinator"
class: solution
topic: "unit-comment-not-install-evidence"
description: "A unit file's comment saying \"installed by bootstrap\" is not evidence it is installed; list-timers on the account and grep bootstrap.py for the unit name"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5ffa38ad21028ac2
---

## A unit file's comment saying "installed by bootstrap" is not evidence it is installed; list-timers on the account and grep bootstrap.py for the unit name

j562 (2026-11-03): runtime/control/agent-fabric-drain.service said "installed by bootstrap.py on the
fabric-coordinator account(s) only", but tools/fabric/bootstrap.py had no step for it (#419 shipped the
units only), and `systemctl --user list-timers` on the coordinator account showed no drain timer: the
weekly drain collection had never run by schedule. Fixed with bootstrap step 6d (coordinator_timers,
COORDINATOR_UNITS), which also installs agent-fabric-scheduled-red.{service,timer} and removes the fabric's
copies on any other role; pushed onto python-dev-02's j109 branch.

**Why:** a timer that is never installed fails silently, the way the red nightly did.
**How to apply:** when a change ships a runtime/control unit, check that bootstrap installs it
(grep bootstrap.py for the name) and read back `systemctl --user list-timers` after the upgrade. See
[[checks-need-a-control]].

*References: checks-need-a-control*

*Anchors: `tools/fabric/bootstrap.py::COORDINATOR_UNITS`, `runtime/control/agent-fabric-drain.service::installed by bootstrap.py`*

*Observed 2026-11-03 (fabric-coordinator)*
