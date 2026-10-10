---
role: "fabric-coordinator"
class: workflow
topic: "branch-name-four-segments"
description: "Name branches <host>/<login>/<type>/<what>; fewer segments read as 'names no session' to fabric-pr reply/sessions"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ba05d12857cd7bcd
  - ee23836478a9fb40
---

## Name branches <host>/<login>/<type>/<what>; fewer segments read as 'names no session' to fabric-pr reply/sessions

Name every branch `<host>/<login>/<type>/<what>`, four segments (e.g. `develop-qzapp/user/fix/followups`). The predicate is in `tools/fabric/github/pr_reply.py` (at least four non-empty segments, the first not an automation prefix), reused by `fabric-pr reply`, `fabric-pr sessions` and `fabric-pr post-review`. A three-segment name reads as "names no session": `fabric-pr reply` treats the PR as unowned and leaves every answered thread open until resolved by hand.

**How to apply:** branch off origin/main with a type segment (fix, feat, docs, drain...). A remote branch of the same name left from an earlier PR is not overwritten (that is a force push); pick a new name.

*Observed 2026-10-10 (fabric-coordinator)*
