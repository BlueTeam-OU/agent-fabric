---
role: "python-dev"
class: domain
topic: "dead-pid-fixture-must-exceed-pid-max"
description: "a test's \"dead\" pid must be 2**22 + 1 or more; 999999 or 2**22 - 5 can be live on a long-running host (pid_max 4194304)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f14af256cdc0c5d0
---

## a test's "dead" pid must be 2**22 + 1 or more; 999999 or 2**22 - 5 can be live on a long-running host (pid_max 4194304)

develop-qzapp's pid counter passed one million (pid_max 4194304, 2026-10-09). The literal 999999
in tests/test_trial_merge.py and tests/test_trial_merge_cli.py could then be a live process,
and both sweep cases failed in a full suite run but passed alone; a live pid in the slot reproduced
the exact failures. Fixed in #129 (249af53f), and tests/test_fabric_status.py's 2**22 - 5 (351476cd),
found by the review because my grep looked only for literals.

**Why:** Linux pids stay below pid_max, whose ceiling is 2**22; anything below can be assigned, and
a liveness check that counts EPERM as alive also sees other accounts' processes.

**How to apply:** a dead pid in a fixture is `2**22 + 1` (or a reaped child's pid); search for
the class by expression too (`2 ** 22`, `pid`), not only by digits; prove each case with a live
pid in the slot as the control.

*Observed 2026-10-08 (python-dev)*
