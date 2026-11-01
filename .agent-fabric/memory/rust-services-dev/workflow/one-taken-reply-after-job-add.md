---
role: "rust-services-dev"
class: workflow
topic: "one-taken-reply-after-job-add"
description: "Taking a REQUEST: create the job first, read its branch from fabric-jobs show, then send one 'taken' REPLY; later facts go in a delivery, not a second 'taken'"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
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

*Observed 2026-10-25 (rust-services-dev)*
