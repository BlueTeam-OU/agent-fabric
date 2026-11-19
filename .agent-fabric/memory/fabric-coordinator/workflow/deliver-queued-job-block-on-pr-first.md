---
role: "fabric-coordinator"
class: workflow
topic: "deliver-queued-job-block-on-pr-first"
description: "a queued job whose work landed on another job's PR — deliver refuses queued; block it on that pr: first, then deliver"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 41919f25ee288dc8
---

## a queued job whose work landed on another job's PR — deliver refuses queued; block it on that pr: first, then deliver

2026-11-09 (j708): python-dev-03's REQUEST for an ADR-029 amendment was queued as j708 and done as one commit
(f786ec8c) on #527 inside my active j703. `fabric-jobs deliver j708 <pr>` refused: "deliver takes a job that is
active or blocked" (ADR-037 rule 14). `start` would need a fresh session (rule 3). What worked without either:
`fabric-jobs block j708 --on pr:<owner/repo>#<n> "<where the work is>"`, then `fabric-jobs deliver j708 <owner/repo>#<n>`;
the hourly sweep closes it when the PR merges. Related: [[jobs-and-switching]].

*References: jobs-and-switching*

*Anchors: `tools/fabric/jobsparts/verbs.py`*

*Observed 2026-11-09 (fabric-coordinator)*
