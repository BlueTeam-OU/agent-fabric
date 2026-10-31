---
role: "devex-tooling"
class: workflow
topic: "jobs-reply-artifact-names-request"
description: "fabric-jobs artifact reply:<id> names the message answered (IN-REPLY-TO), not your reply's own id; artifacts are append-only"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 43caed66ab94e69d
---

## fabric-jobs artifact reply:<id> names the message answered (IN-REPLY-TO), not your reply's own id; artifacts are append-only

`fabric-jobs deliver <job> reply:<MESSAGE-ID>` is checked by tools/fabric/jobsparts/settle.py `replied()`: an outbound REPLY in the journal whose in_reply_to is that id. So the id is the REQUEST you answered, never the id gzcoord-send minted for your reply. A wrong one blocks `fabric-jobs next` ("not in this login's journal as sent") and `deliver` only appends; the fix was runtime/identity.py `update_jobs(mutate)` replacing that artifact under the agent lock (j129, 2026-10-14). A full commit sha is also accepted as an artifact.

*Anchors: `tools/fabric/jobsparts/settle.py::replied`*

*Observed 2026-10-14 (devex-tooling)*
