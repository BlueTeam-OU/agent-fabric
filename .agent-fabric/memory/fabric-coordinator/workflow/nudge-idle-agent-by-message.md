---
role: "fabric-coordinator"
class: workflow
topic: "nudge-idle-agent-by-message"
description: An agent that seems idle is nudged by me with a GZCoord message first — never handed to the owner to type into its terminal
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 426896df1684ad53
---

## An agent that seems idle is nudged by me with a GZCoord message first — never handed to the owner to type into its terminal

When an agent sits on queued work, I send it a message myself (a short REQUEST or
INFO TO its login naming the job id and "run fabric-jobs next") before asking the
owner to do anything at its terminal.

**Why:** 2026-10-09 I asked the owner to type into python-dev-03's session; the
owner did it and said I can send the agent a message for this. The owner's time is
the chokepoint, not a relay for nudges.

**How to apply:** queue the job (`fabric-ctl <login> jobs-add`, [[request-needs-a-job]]),
send the nudge, give it time; only if presence shows no session, or the message is
still unanswered well after, tell the owner — with the evidence (jobs list,
presence, the message id).

*References: request-needs-a-job*

*Observed 2026-10-09 (fabric-coordinator)*
