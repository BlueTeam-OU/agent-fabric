---
role: "fabric-coordinator"
class: solution
topic: "fresh-job-test-needs-listed-job"
description: "a launch test of a fresh relaunch's job must use a job the sandbox list holds, or opening_prompt keeps AGENT_FABRIC_FRESH_JOB and hides the bug"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2477a7da6c761dfe
---

## a launch test of a fresh relaunch's job must use a job the sandbox list holds, or opening_prompt keeps AGENT_FABRIC_FRESH_JOB and hides the bug

`opening_prompt` (tools/fabric/launcher/session.py) deletes `AGENT_FABRIC_FRESH_JOB` only inside `if line:`, when
`jobs.py show <job> --line` finds the job. A test whose job is not in the sandbox's list (group 6's j417 in
tests/test_launch_cli.py) keeps the variable and so passes code that reads it after the prompt is built. The #395 F3 bug
(gateway refusal after the prompt, RESTART NOT COMPLETED with no job) was only caught by group 8's case, which adds a job
with jobs.py first and fails on the old reader (j421, 9deeaa35 on #485). Since then the job rides
`AGENT_FABRIC_RESTARTING=fresh:<job>`.

**How to apply:** any test of what happens after opening_prompt in a fresh relaunch adds the job to the sandbox list and
has a control showing the job reached the prompt. See [[checks-need-a-control]].

*References: checks-need-a-control*

*Anchors: `tools/fabric/launcher/session.py::del os.environ["AGENT_FABRIC_FRESH_JOB"]`, `tools/fabric/launch.py::base[RESTARTING] = f"fresh:{job}"`*

*Observed 2026-11-04 (fabric-coordinator)*
