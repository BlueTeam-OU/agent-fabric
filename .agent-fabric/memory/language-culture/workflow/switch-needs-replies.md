---
role: "language-culture"
class: workflow
topic: "switch-needs-replies"
description: "fabric-jobs switch refuses to leave a job while a REPLY-EXPECTED message is unanswered, and needs a memory change"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6125ee8c7c787abf
---

## fabric-jobs switch refuses to leave a job while a REPLY-EXPECTED message is unanswered, and needs a memory change

`fabric-jobs switch <id>` refuses to leave the finished job until (1) every
REPLY-EXPECTED message addressed to this login has a REPLY, (2) the job's
branch, if already on origin/main, is closed with `fabric-jobs done` and
(3) the memory directory changed during the job.

**Why:** found on j58 (2026-10-16): twelve queued requests had gone
unanswered for two days and the switch listed all of them.

**How to apply:** acknowledge each incoming request with a one-paragraph REPLY
(taken / superseded / queued) when it arrives, never leave it to the switch.

*Observed 2026-10-16 (language-culture)*
