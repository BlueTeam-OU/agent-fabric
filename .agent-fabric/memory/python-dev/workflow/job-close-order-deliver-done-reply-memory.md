---
role: "python-dev"
class: workflow
topic: "job-close-order-deliver-done-reply-memory"
description: "Closing a job after its PR merges: fabric-pr arm needs --basis even with --authorization; switch refuses until done, reply sent and memory changed"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dbb90c21e9c013cf
---

## Closing a job after its PR merges: fabric-pr arm needs --basis even with --authorization; switch refuses until done, reply sent and memory changed

After a security-boundary PR is authorized: `fabric-pr arm N --basis "<line>" --authorization <decision id>` (the dry-run alone refuses without `--basis`; it merges in the same call). Then `fabric-jobs switch` refuses until the job is `done` (a merged PR is done, not delivered), every REPLY-EXPECTED message is answered (a newly queued REQUEST counts), and a memory file changed during the job. A `switch` run right after the merge can show an ImportError from half-pulled tools; run it again.

**Why:** j59 (PR 351, 2026-10-21) needed three switch attempts for these three reasons.
**How to apply:** do deliver/done, answer pending REQUESTs and write the memory before the first `fabric-jobs switch`.

*Anchors: `tools/fabric/github/arm.py::--basis`*

*Observed 2026-10-22 (python-dev)*
