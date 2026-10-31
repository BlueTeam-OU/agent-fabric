---
role: "fabric-coordinator"
class: workflow
topic: "ancestor-is-not-landed-check-reverts"
description: "before relying on \"commit X is on main\", grep main for its content or a Revert — merge-base --is-ancestor says yes after a revert"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e87eecab00b382f3
---

## before relying on "commit X is on main", grep main for its content or a Revert — merge-base --is-ancestor says yes after a revert

`git merge-base --is-ancestor X origin/main` and `git branch -r --contains X` both answer yes for a commit that a later commit reverted. j389 (2026-10-30): bc73f87a (episodic verified sender) was an ancestor of main, the job note said "episodic half on #417's branch", yet 13f20fd1 had reverted it in #417 round 9 (F14, F15) — found only when the folded carrier test failed with the claim as sender.

**Why:** a job note or my own summary written before a review round goes stale silently; ancestry is not content.

**How to apply:** before building on "X landed", run `git log origin/main --oneline -S'<a line X added>' -- <file>` (shows the add and any revert) or grep the file on origin/main. Pairs with [[accepted-only-when-on-main]] and [[readded-job-check-tree-first]].

*References: accepted-only-when-on-main, readded-job-check-tree-first*

*Anchors: `tools/fabric/episodic.py::sender_verified`*

*Observed 2026-10-30 (fabric-coordinator)*
