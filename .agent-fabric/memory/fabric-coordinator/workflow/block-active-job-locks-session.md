---
role: "fabric-coordinator"
class: workflow
topic: "block-active-job-locks-session"
description: "blocking the job this session is working makes the job-copy hook refuse every later push or commit here; keep it active while this session still folds or pushes for it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7fc3a34250a5cfd6
---

## blocking the job this session is working makes the job-copy hook refuse every later push or commit here; keep it active while this session still folds or pushes for it

2026-10-31, j468: I blocked j468 on devex-tooling's j261 while #437 still had an unpushed review-fix (a9590d52). The PreToolUse job-copy hook then refused `git push`: "This session worked job j468, which has left active, and no job is active". `fabric-jobs start j468` cleared it, but only as its own Bash call: the hook reads the job state before a compound command's first part runs.

**Why:** ADR-037 rule 3's fence treats a session whose job left `active` as between jobs.

**How to apply:** push and commit first, then block. If this session will fold the awaited delivery itself, leave the job active with the wait in its note, and block only before `fabric-jobs switch`. Related: [[park-a-job-block-not-pause]], [[block-on-job-not-request-after-reply]].

*References: block-on-job-not-request-after-reply, park-a-job-block-not-pause*

*Anchors: `runtime/claude-code/hooks/job-copy-guard.py::which has left`*

*Observed 2026-10-31 (fabric-coordinator)*
