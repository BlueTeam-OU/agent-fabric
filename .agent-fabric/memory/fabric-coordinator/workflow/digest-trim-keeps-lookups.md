---
role: "fabric-coordinator"
class: workflow
topic: "digest-trim-keeps-lookups"
description: "shortening a DIGEST bullet — diff the entry's word set against main and look up every word that left, before committing"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2b061f281d272e7d
  - 3f860550bf1a01f3
---

## shortening a DIGEST bullet — diff the entry's word set against main and look up every word that left, before committing

Shortening a DIGEST bullet silently drops lookup keys: `adr check` counts words only and cannot tell
a cut article from a cut key. 12424efe lost ADR-022's `Monitor` (#416 review F5); j652 lost
ADR-029's `resume`. The per-entry 250-word total that forced most trims is gone since 2026-11-09
(the budget is 60 words per bullet, [[digest-entry-over-250-words]]), so a trim is now only of the
bullet that is too long.

**Why:** the review is otherwise the first thing that notices a lost key.

**How to apply:** before committing a DIGEST edit, compute the entry's word set on origin/main minus
the new one (a short python over `git show origin/main:docs/adr/DIGEST.md`) and run `adr.py lookup`
on each word that left; drop a keyword only when the entry's body already contains it.

*References: digest-entry-over-250-words*

*Anchors: `tools/fabric/adr.py::DIGEST_BULLET_WORDS`*

*Observed 2026-11-09 (fabric-coordinator)*
