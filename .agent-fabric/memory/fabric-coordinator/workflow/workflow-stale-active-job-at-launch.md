---
role: "fabric-coordinator"
class: workflow
topic: "workflow-stale-active-job-at-launch"
description: "a fresh session launched for job X can find an earlier job still active elsewhere; the job-copy guard then refuses X's publishing commands until that job is settled"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 89576b5b066209b3
---

## a fresh session launched for job X can find an earlier job still active elsewhere; the job-copy guard then refuses X's publishing commands until that job is settled

2026-11-11: a session launched for j779 (arm gzapp#1246) found j713 (stripped-nightly red) still `active` in its own worktree, with its blocker (python-dev-03 j128, BlueTeam-OU/agent-fabric#559) merged. The ADR-037 rule 3 guard refused `fabric-pr arm` in gzapp until j713 was settled. Settle it from evidence first: the copy clean with nothing ahead of origin/main, and a green `workflow_dispatch` run of the workflow after the fix merged (43068612114). Then `fabric-jobs done --no-artifact` and `switch <id>`. `switch` also refuses until the memory directory has changed during the job.

*Anchors: `tools/fabric/jobsparts/settle.py::memory_changed`*

*Observed 2026-11-11 (fabric-coordinator)*
