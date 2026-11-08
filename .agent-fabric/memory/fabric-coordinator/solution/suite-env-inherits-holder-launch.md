---
role: "fabric-coordinator"
class: solution
topic: "suite-env-inherits-holder-launch"
description: "a suite red only on a locale holder's login — check what its env copy inherits from the running launch (TZ, AGENT_FABRIC_LAUNCH_*)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 978167cdc3ffbc28
---

## a suite red only on a locale holder's login — check what its env copy inherits from the running launch (TZ, AGENT_FABRIC_LAUNCH_*)

A holder's launch exports TZ (its holder.json timezone) and stamps
AGENT_FABRIC_LAUNCH_STORE_SHA / _ADDENDA_COMMIT; user's launch has neither.
A suite that copies os.environ into a case inherits them: test_launch_cli's
`base` kept TZ (groups 7, 10 red), test_addenda's `role_env` kept the stamps
("a launch that stamped nothing" red) — OBSERVATION 01a1aad1 from
language-culture-ge, fixed edea4b90 on #488 (j619) by filtering TZ and
AGENT_FABRIC_* in the cases. The control without a second login: run the
file with `TZ=Asia/Tbilisi` or planted `AGENT_FABRIC_LAUNCH_STORE_SHA=aaa…`.
Pinning in the case, not tests/run.py run_environment, keeps a file run
alone (how reporters check) clean too. Related: [[login-dependent-test-plant-own-entry]].

*References: login-dependent-test-plant-own-entry*

*Anchors: `tests/test_launch_cli.py::"LOGNAME", "TZ"`, `tests/test_addenda.py::startswith(("GIT_", "AGENT_FABRIC_"))`*

*Observed 2026-11-05 (fabric-coordinator)*
