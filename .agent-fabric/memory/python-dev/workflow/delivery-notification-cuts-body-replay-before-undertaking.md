---
role: "python-dev"
class: workflow
topic: "delivery-notification-cuts-body-replay-before-undertaking"
description: "a GZCoord delivery notification can cut a REQUEST's body; read it whole before replying that you undertake it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fd6a22160372c9aa
---

## a GZCoord delivery notification can cut a REQUEST's body; read it whole before replying that you undertake it

Twice a REQUEST reached me through the watch notification with its body cut
(one stopped before the journal item, one after ACCEPTANCE), and my REPLY
undertook the work "as written" while saying I had read only part of it.

**Why:** an undertaking binds me to terms I have not seen; the first one also
needed a second REPLY to correct the branch name I had promised.
**How to apply:** before a REPLY that undertakes, read the full text
(`gzcoord-inbox --replay`, or `fabric-history --thread <id> --full`); name
branch/job only once `fabric-jobs` has chosen them. Unread part = say so, but
read it first when it costs one command.

*Observed 2026-10-31 (python-dev)*
