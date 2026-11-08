---
role: "python-dev"
class: solution
topic: "j109-scheduled-red-merged"
description: "j109 scheduled_red.py merged as #462; newest run is the verdict, dropped counts closed (F2 deferred), arm needed owner's word"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ee6e93679bc382bd
---

## j109 scheduled_red.py merged as #462; newest run is the verdict, dropped counts closed (F2 deferred), arm needed owner's word

PR #462 merged 2026-11-03 on head 0a6a2073 (2 work, 2 fix): `tools/fabric/github/scheduled_red.py` plus `tests/test_scheduled_red.py`, with the coordinator's unit/timer/bootstrap commit ab0461e8 on the same branch.

- Only the newest completed run is the verdict; an older unreadable run becomes UNKNOWN and ends the red-since count ("or earlier"). An older run with no integer id is said as "a run", never run 0.
- A marked job in state dropped counts as closed (fabric-jobs OPEN set), though the request said "any state but done". Deferred as P3 `ab0461e8:F2`; the owner gave no ruling. A flip is a small follow-up if asked.
- Boundary files (unit, timer, bootstrap.py) with 2 work commits armed only on the owner's typed "arm 462". `--defer` takes the head8 of the review that raised the finding (ab0461e8), not the current head.

**Why:** records the F2 disagreement and the defer-label trap.
**How to apply:** a follow-up on dropped handling edits `open_marked`/`file_job` and the "a dropped marked job" test; use `--defer "<raising review head8>:F<n>"`.

See [[security-boundary-arm-needs-owner]].

*References: security-boundary-arm-needs-owner*

*Anchors: `tools/fabric/github/scheduled_red.py::open_marked`, `tools/fabric/github/scheduled_red.py::red_since`*

*Observed 2026-11-03 (python-dev)*
