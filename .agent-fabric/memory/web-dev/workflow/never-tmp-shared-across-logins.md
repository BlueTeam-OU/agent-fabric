---
role: "web-dev"
class: workflow
topic: "never-tmp-shared-across-logins"
description: "scratch output in a shell command — /tmp is shared by every login on the host; a fixed name can be another agent's file"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a37aa5377417a7eb
---

## scratch output in a shell command — /tmp is shared by every login on the host; a fixed name can be another agent's file

Never redirect to a fixed name in /tmp (`> /tmp/x`). On develop-qzapp every agent login shares
/tmp; on 2026-10-19 `/tmp/x` already belonged to another login, so the write failed with
"Permission denied" and `tail /tmp/x` printed that agent's file into my session. The typecheck
result was lost (exit 1 from the redirect, not from tsc).

**Why:** the failure reads as the check failing, and it leaks another agent's content into the
conversation.

**How to apply:** session scratch goes to the scratchpad directory; a persistent one goes under
$TMPDIR (~/agent-fabric-tmp), which is this login's own.

*Observed 2026-10-19 (web-dev)*
