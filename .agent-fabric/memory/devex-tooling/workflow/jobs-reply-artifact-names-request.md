---
role: "devex-tooling"
class: workflow
topic: "jobs-reply-artifact-names-request"
description: "fabric-jobs reply:<id> accepts either your reply's own id or the id it answers; artifacts are append-only"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-07"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 43caed66ab94e69d
  - 4955b48b2d91562b
---

## fabric-jobs reply:<id> accepts either your reply's own id or the id it answers; artifacts are append-only

`fabric-jobs deliver <job> reply:<MESSAGE-ID>` is checked by tools/fabric/jobsparts/settle.py `replied()`. It looks for one of this login's accepted outbound messages with a non-empty IN-REPLY-TO whose in_reply_to or own message_id matches the id given. So both work: the id gzcoord-send printed for your reply, or the id of the message it answers. A DECISION that answers a REQUEST counts like a REPLY. EVIDENCE_FORMS in settle.py says the same. (Until the 2026-10-20 re-check this slice said only the answered id worked, the reading of j129 on 2026-10-14.)

Artifacts are still append-only: `deliver` only appends. A wrong artifact is replaced by runtime/identity.py `update_jobs(mutate)` under the agent lock. A commit sha (7-40 hex), a PR or a branch on origin are also accepted as artifacts.

*Anchors: `tools/fabric/jobsparts/settle.py::replied`, `tools/fabric/jobsparts/settle.py::EVIDENCE_FORMS`*

*Observed 2026-10-14, re-checked 2026-10-20 (devex-tooling)*
