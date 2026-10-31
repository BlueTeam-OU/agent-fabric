---
role: "architect-cto"
class: workflow
topic: "owner-merge-asap-on-another-roles-pr-is-a-drive"
description: "The owner's \"merge #N asap\" on a PR another role owns is a drive, not an arm; read the gate first, since a queued PR or a forced-order red needs no message at all"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fc384ed86f002af6
---

## The owner's "merge #N asap" on a PR another role owns is a drive, not an arm; read the gate first, since a queued PR or a forced-order red needs no message at all

When the owner says "merge #A and #B asap" and neither PR is mine
(gzapp #1167/#1169, 2026-10-25): read `fabric-pr gate` for each in the
project's working copy before anything else. One was already queued
(`armed=no queue=1`, which is queued; see
[[reflection-a-queued-pr-reports-no-automerge-request]]) and needed no
message. The other's only red was the migration-contiguity check, a
forced order on the first, not a defect. The drive is one REQUEST to
the owner of the blocked PR carrying the owner's word, the step list
(fold, carry, ready, review, arm by count) and "no AUTHORIZES needed"
when the count is above the minimum; a job blocked on that reply; and
the owner answered with each PR as "#N (W work, F fix)" plus the one
fact that decides its state.

**Why:** the owner decides from counts, and a message to a PR that is
already queued costs its owner a session turn for nothing.

**How to apply:** gate both, name what is already moving, message only
the one that is blocked, and say which role holds each step.

*References: reflection-a-queued-pr-reports-no-automerge-request*

*Observed 2026-10-25 (architect-cto)*
