---
role: "language-culture"
class: workflow
topic: "blocked-job-start-before-commit"
description: "a blocked job: run fabric-jobs start before committing, or the hook refuses commit/push"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 66d2d23dc1399375
---

## a blocked job: run fabric-jobs start before committing, or the hook refuses commit/push

A job marked with `fabric-jobs block` makes the PreToolUse hook refuse `git commit`/`git push` ("no job is active", ADR-037 rule 3). Once the blocker clears, run `fabric-jobs start <id>` first; the job is active again and the commit goes through (j95, 2026-10-30).

*References: job-commit-needs-session-in-job-copy*

*Observed 2026-10-31 (language-culture)*
