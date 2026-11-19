---
role: "python-dev"
class: workflow
topic: "queued-jobs-close-needs-start-and-switch-wants-the-reply"
description: "closing queued jobs a merged PR covers, and what fabric-jobs switch refuses at the end"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f5fdbf697176f639
---

## closing queued jobs a merged PR covers, and what fabric-jobs switch refuses at the end

j137 (2026-11-16): `fabric-jobs done` takes only an active or delivered job, so queued jobs that a merged PR already covers (j136, j137 on #630) are closed with `fabric-jobs start <id>` then `done <id> <owner/repo#N>`. `fabric-jobs deliver` on a merged PR is refused ("the job is done, not delivered"). `switch` also refuses while any REPLY-EXPECTED: yes message is unanswered, including one that arrived after the work; answer first, and write a memory in the same job.

**Why:** a request that arrives while the last job is closing is queued as a job at once, and the next `switch` names it as the blocker.
**How to apply:** after the merge, read `fabric-jobs list` for queued twins of the PR, close them, send the pending REPLYs, then switch.

*Observed 2026-11-16 (python-dev)*
