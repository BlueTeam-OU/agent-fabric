---
role: "web-dev"
class: workflow
topic: "pr-status-names-its-head"
description: "Before telling anyone a PR is green, reviewed or 'gate met': which head that was true of, and what a later push does to it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 11897ce7e6a5b854
---

## Before telling anyone a PR is green, reviewed or 'gate met': which head that was true of, and what a later push does to it

A PR status ("green", "review gate met", "zero threads") is true of one
head sha, and any push after it voids the status. Twice in one week I
relayed a status that was no longer true: once "green", when a commit
pushed two commits later had turned a required check red; once "gate met"
for a reviewed head that two later fixes had replaced while the relay was
on its way to the owner.

**Why:** the reader passes the status on to whoever arms or merges, and
"it was green when I looked" is not a status.

**How to apply:** every status names its sha ("gate met at <sha>: review
verdict on <sha>, N checks pass, 0 threads"). After each push, read the
checks and the review against the new head before you say anything about
the PR again. If a status already sent has gone stale, correct it to the
person carrying it before they relay it.

Sources (GZCoord): 01a0beca-2428-7e95-b147-ac36de547d5d,
01a0bec8-60bf-7c3b-baa5-e86bed108aef, 01a0c243-9bbe-7336-b24a-aaac55e72977.

*Anchors: `policies/pull-requests/SKILL.md::a posted review of the head`*

*Observed 2026-10-18 (web-dev)*
