---
role: "python-dev"
class: workflow
topic: "in-process-test-seams-reload-and-barriers"
description: "j138 #635 — speeding suites by running jobs.main/ctl.main in process: capture the seam module at load, assert-nothing waits need a barrier after the event, profile before cutting"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fd00ba776d567abf
---

## j138 #635 — speeding suites by running jobs.main/ctl.main in process: capture the seam module at load, assert-nothing waits need a barrier after the event, profile before cutting

Method that worked (#635, 2026-11-16/17): profile subprocess starts first (Popen wrapper counting argv), then (1) swap the one expensive command a verb runs for an empty script through a module constant (`leave_sweep.BRANCHES`), keeping the real one in its own section; (2) run the reader/verb in process (`jobs.main`, `ctl.main`, `episodic.main`) and keep one case per command through the bare entry; (3) replace assert-nothing sleeps by a later request answered on the same ordered carrier.

**Why:** the review found three real defects in my own cut. A seam set on `sys.modules["fabric_jobs"]` stops applying once another test loads jobs.py again (each load replaces the package): capture the module at the load that built the in-process main. An arrival logged before the drop's `return` is no bound for "nothing answered": use a barrier request, 12 runs of the mutant (3/12 green before). Shortening a stub relay's quiet poll made it worse (polling storm): measure wall and CPU.

**How to apply:** report wall and user+sys under env -i; a mutation whose target the case never read (journal `ts`, jobs reads `recorded_at`) is the wrong mutation, not a gap. Suites other lanes own (lint walk, new_agent's ~700 execs) are reported with the profile, not cut. Coordinator word for arming below the minimum names its message id in `--basis`.

*Observed 2026-11-16 (python-dev)*
