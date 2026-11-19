---
role: "python-dev"
class: workflow
topic: "repeat-request-new-job-j141"
description: "a request resent under a new message id queues a new job; answer from the delivered job's artifacts, not new work"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f94b3c7b46fe3093
---

## a request resent under a new message id queues a new job; answer from the delivered job's artifacts, not new work

The owner's relay resent the j140 request (same two items, new message id) and it queued as j141. Nothing new was due: `fabric-jobs start` then `deliver` with the merged PR and the new request id as `reply:` closed it, after a REPLY that names the earlier answers.

**Why:** `switch` refuses to leave a job while a REPLY-EXPECTED message is unanswered and the memory directory unchanged, so even a duplicate needs a REPLY and a memory note.
**How to apply:** on a queued job whose subject matches a delivered one, check `fabric-jobs list` and `fabric-pr gate <n>` first; reply with the ids, deliver, do not redo.

*Anchors: `tools/fabric/jobs.py::deliver`*

*Observed 2026-11-14 (python-dev)*
