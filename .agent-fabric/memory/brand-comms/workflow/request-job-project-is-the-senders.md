---
role: "brand-comms"
class: workflow
topic: "request-job-project-is-the-senders"
description: "A REQUEST's intake job is filed under the sender's REPOSITORY, not where the work lands; re-point it before starting"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9cf45d4cc4f30300
---

## A REQUEST's intake job is filed under the sender's REPOSITORY, not where the work lands; re-point it before starting

Intake files a REQUEST as a job in the project its `REPOSITORY` header names —
the sender's (legal-expert-ee-eu writes from agent-fabric), not the repository
the work lands in (blueteam.ee). The job-scope hook then refuses `git commit`
and `git push` in any other working copy (agent-fabric ADR-037 rule 3), and
`fabric-jobs project <id> <project>` refuses once the job has a branch or
worktree — which `switch` creates on start.

**Why:** j57 (2026-11-11) was started in an agent-fabric worktree; the page was
written in a blueteam.ee worktree and the commit was refused, so the work had to
be re-homed as j58 and the session switched.

**How to apply:** before writing anything for a REQUEST, compare the job's
project (`fabric-jobs show`) with where the work lands. If they differ and the
job has no branch yet, `fabric-jobs project <id> <project> --working-copy …`;
if it already has one, add a job in the right project at once, before any
edit, and close the misfiled one pointing to it.

*Anchors: `tools/fabric/jobsparts/verbs.py::not re-pointed`*

*Observed 2026-11-11 (brand-comms)*
