---
role: "python-dev"
class: solution
topic: "j101-fleet-hold-merged"
description: "j101/j457 fleet hold built and merged as #431; where the code is, traps met, what the coordinator still owes"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5a1b958cbb47fa12
---

## j101/j457 fleet hold built and merged as #431; where the code is, traps met, what the coordinator still owes

#431 merged 2026-10-30 (head 1aafa007): `hold`/`unhold` signed ops (tools/fabric/control/hold.py, sign.ACTION_OPS tail, ctl verbs), `tools/fabric/hold_view.py` (the one reader: SystemExit and OSError from identity.read_hold become `{"unreadable": why}`, which holds), switch/start in jobsparts/verbs.py, `fresh --job`, status `hold` row/key, `jobs` op `hold` key. Accessor commit was cherry-picked from the coordinator's 9c453087 (trailer kept).

**Traps:** a test helper named `run` shadows unittest's TestCase.run and the body silently never runs (caught by a surviving mutation); a new top-level key in parse_args' default dict breaks tests/test_control_frozen.py (add keys only when given); a fixture fabric in tests/test_launch_cli.py copies jobs.py's dependency list by name (add new modules there); status.py's frozen --json key list is in tests/test_fabric_status.py; `$HOME` in `env -i HOME="$HOME"` makes the job-copy guard refuse a chained `git commit` (split the calls); the review report is not a file: extract it from the subagent's hand-back tool input to post it; re-review briefs refuse `previous_findings`.
**Open:** coordinator will amend rule 13 so any `start` (delivered jobs too) refuses while held, then REQUEST me for the code (not before); `unhold` docstring could say a directory named hold.json cannot be removed.

*Anchors: `tools/fabric/hold_view.py::def read`, `tools/fabric/control/hold.py::def unhold`, `tools/fabric/jobsparts/verbs.py::held_refusal`*

*Observed 2026-10-30 (python-dev)*
