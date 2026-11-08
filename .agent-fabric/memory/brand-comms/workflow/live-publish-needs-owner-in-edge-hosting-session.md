---
role: "brand-comms"
class: workflow
topic: "live-publish-needs-owner-in-edge-hosting-session"
description: "When asking edge-hosting to publish a site commit, expect the live upload to wait for the owner's word in edge-hosting's own session; a relayed \"the owner asked\" does not cover it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ac133a6af1ec4778
---

## When asking edge-hosting to publish a site commit, expect the live upload to wait for the owner's word in edge-hosting's own session; a relayed "the owner asked" does not cover it

A publish REQUEST to edge-hosting (blueteam.ee, and by the same rule any site
it serves) is taken at once, but the `--live` step runs only after the owner
confirms it in edge-hosting's own session, against the commit and the dry
run's counts. If main moves first, edge-hosting asks about the new head.

**Why:** edge-hosting treats a relayed owner instruction as not enough for a
live upload; it held to this on both publishes of 2026-10-30 (19858f4,
61e5168).

**How to apply:** when the owner asks me for a publish, tell them in the same
answer that edge-hosting will ask them to confirm it in its session, and do not
call the site published until edge-hosting's REPLY names the uploaded commit
and its served-bytes check. Put in ACCEPTANCE what I expect to upload (the file
count, which pages), so the dry run can be compared against it.

*Anchors: `blueteam.ee:deploy/deploy.sh::--live`*

*Observed 2026-10-31 (brand-comms)*
