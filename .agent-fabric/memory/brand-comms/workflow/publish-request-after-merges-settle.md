---
role: "brand-comms"
class: workflow
topic: "publish-request-after-merges-settle"
description: "When asking edge-hosting to publish a site, wait until the owner's run of merges settles; if main moves after the request, send an update naming the new commit and its delta."
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bbb61af0b1796570
---

## When asking edge-hosting to publish a site, wait until the owner's run of merges settles; if main moves after the request, send an update naming the new commit and its delta.

A publish request to edge-hosting names one commit of the site's main.
Twice on one afternoon (blueteam.ee, 2026-10-15) the owner merged
another PR minutes after I asked: 7611241 was superseded by c4dfe15,
and f23b045 by 4da86cb. Each time I had to send a follow-up, and once
edge-hosting uploaded twice.

**Why:** the owner often merges a run of small PRs in a row (styling,
logo, favicon). A request sent mid-run is out of date before it is
read, and every extra upload is another round of live checks.

**How to apply:**
- Before you ask for `<commit>` to be published, ask the owner (or check
  your own open PRs) whether more merges are coming, and send one
  request once main has settled.
- If main moves after the request anyway, send an INFO that replies to
  the request. It names the new commit, what it adds since the old one,
  and that uploading it on top of the old one is enough.
- A go names content, not "latest": "the go is for `<commit>`'s content;
  a later commit of mine names itself" (01a12a87-0b59). Edge-hosting
  never publishes something nobody named.

*Anchors: `identities/roles/brand-comms/charter.md::hosting, names and edge that serve a site`*

*Observed 2026-10-18 (brand-comms)*
