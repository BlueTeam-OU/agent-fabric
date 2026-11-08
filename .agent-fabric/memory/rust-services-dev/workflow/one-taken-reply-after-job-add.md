---
role: "rust-services-dev"
class: workflow
topic: "one-taken-reply-after-job-add"
description: "Taking a REQUEST: create the job first, read its branch from fabric-jobs show, then send one 'taken' REPLY; later facts go in a delivery, not a second 'taken'"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1553f260b7bf9620
  - 7966df98369bc9b6
---

## Taking a REQUEST: create the job first, read its branch from fabric-jobs show, then send one 'taken' REPLY; later facts go in a delivery, not a second 'taken'

Twice in one week a taken REQUEST cost the requester extra messages:
- j63: three REPLYs for one take. The first named a branch I made up. The second
  corrected it to the one fabric-jobs had created. The third restated the take.
- j64: two "taken" REPLYs ten minutes apart. The second added a hand measurement
  that changed the scope.

The branch name is the acknowledgement (team.md), so it must be the real one.

**How to apply:** when you take a REQUEST:
1. Run `fabric-jobs add` (or let delivery queue it), then `fabric-jobs show <job>`,
   and copy the branch from there.
2. Check the request's claims against the tree.
3. Send ONE REPLY with IN-REPLY-TO. It carries the branch, what you checked, and what
   you undertake.
4. If something you measure later changes the scope, it goes in the next delivery
   REPLY (results, PR open), not in a second "taken".

**When the job is queued, not started (2026-11-03, j68):** a delivered REQUEST is queued
without a branch. `fabric-jobs switch` refuses to leave the finished job until the request
is answered, and it creates the branch only after that. So the intake REPLY cannot name
the branch. In it, say the branch and anything else the acceptance asks for (such as a
pinned build) follow from the job's own session. Don't invent a branch name. The branch
is `<host>/<login>/feat/j<N>-<slug of the title>`, but read it from `switch`'s output,
never predict it. (REPLY 01a1a07b-977a-7bf6-a86f-034f81091d55.)

*Observed 2026-11-03 (rust-services-dev)*
