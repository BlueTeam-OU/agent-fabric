---
role: "fabric-coordinator"
class: workflow
topic: "request-needs-a-job"
description: "A REQUEST becomes a job on the addressee's list by its inbox intake (2026-10-10); read their list after the send, jobs-add only if no job appeared"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 195b39a33eee8629
---

## A REQUEST becomes a job on the addressee's list by its inbox intake (2026-10-10); read their list after the send, jobs-add only if no job appeared

A REQUEST over GZCoord is only advisory: an agent whose session is idle with an
empty job list (python-dev-03, 2026-10-09: three REQUESTs over an hour, no
answer, `fabric-ctl python-dev-03 jobs` empty) never picks it up. The owner
pointed it out. So when I assign work, I also put it on the assignee's list:
`fabric-ctl <login> jobs-add --topic T --project P --priority P -- "<title>"`
(title one line, at most 300 characters; cite the REQUEST's message id). Before
saying "no answer", read `fabric-ctl <login> jobs` — an empty list means the
work was never queued, not that the agent declined it.

**Changed 2026-10-10:** the addressee's inbox intake now makes the job from the REQUEST
itself (five correction REQUESTs each became a job, j65/j80/j16/j8/j76, within a minute).
My jobs-add on top made five duplicates. Now: send, then read `fabric-ctl <login> jobs`;
jobs-add only when no job carries the REQUEST's subject (an agent with no session running
yet still needs it).

*Observed 2026-10-09 (fabric-coordinator)*
