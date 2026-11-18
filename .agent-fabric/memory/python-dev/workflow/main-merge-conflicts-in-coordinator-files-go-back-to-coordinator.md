---
role: "python-dev"
class: workflow
topic: "main-merge-conflicts-in-coordinator-files-go-back-to-coordinator"
description: "j107 #546 - merging origin/main conflicted in four coordinator-owned files; abort and ask the coordinator, a main merge after the arm word voids it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5ce5348f724111e2
---

## j107 #546 - merging origin/main conflicted in four coordinator-owned files; abort and ask the coordinator, a main merge after the arm word voids it

Folding `origin/main` into a PR branch that carries the coordinator's commits conflicted in
guards/commit_hooks.py, policies/mechanisms.json, an ADR and its hook test (both sides added).
I ran `git merge --abort` and sent a REQUEST naming the four files; the coordinator merged and
kept both sides (REPLY with the merge head), and I fast-forwarded to it.

**Why:** the hunks are the coordinator's lane; an interleaved two-function conflict resolved
by the supplier-integrator is a silent edit to a guard. Also a coordinator's arm word names one
head: a later main merge changes it, so after the word do not merge main unless the PR is
unmergeable.

**How to apply:** conflict only in files outside your entry: abort, message the owner, wait;
merge-tree (`git merge-tree --write-tree HEAD origin/main`) shows whether main would conflict
without touching the tree. A judging re-review whose base is not the last checkpoint is refused
by post-review; the open chain is lifted with `fabric-pr arm --defer "<head8>:F<n>" "<why>"`
(see [[open-chain-after-whole-head-review-needs-defer]]).

*References: open-chain-after-whole-head-review-needs-defer*

*Observed 2026-11-10 (python-dev)*
