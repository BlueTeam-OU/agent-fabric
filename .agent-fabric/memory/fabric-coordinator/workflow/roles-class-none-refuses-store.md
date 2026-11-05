---
role: "fabric-coordinator"
class: workflow
topic: "roles-class-none-refuses-store"
description: "A memory with `roles_class: none` makes harvest_memory refuse the WHOLE store (harvest-failed); private means no roles_class line at all"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 69791dda5b6370d1
---

## A memory with `roles_class: none` makes harvest_memory refuse the WHOLE store (harvest-failed); private means no roles_class line at all

2026-10-31, the drain for j279: `fabric-ctl all memory` returned `harvest-failed` for my agent-fabric store, so none of its 267 memories drained. The cause was five index memories (arming-prs, codex-reviews, dated-threads-and-jobs, external-tools-evaluated, fleet-deck-boot) marked `roles_class: none`. The harvester's error: "roles_class 'none' is not a claim class … refusing rather than guessing where these belong". After I deleted those lines and re-ran `fabric-ctl user memory`, the store was ok and gave 229 claims.

**Why:** the harvester treats any roles_class value that is not a claim class as an error that needs a decision. A missing line is how a memory says it is private.

**How to apply:** to keep a memory out of the corpus, leave out the `roles_class` line; never write `none`. Before a drain, scan each harvest row for `harvest-failed` and read its error, not only the claim counts.

*Anchors: `tools/fabric/harvest_memory.py`*

*Observed 2026-10-31 (fabric-coordinator)*
