---
role: "language-culture"
class: workflow
topic: "close-delivered-jobs-by-ancestry"
description: "when asked to tidy the job list, close a delivered job only when its commit is an ancestor of the target's origin/main; a supplier commit on an open PR keeps its job delivered"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6485e37abcc877cc
---

## when asked to tidy the job list, close a delivered job only when its commit is an ancestor of the target's origin/main; a supplier commit on an open PR keeps its job delivered

A copy or review job of this role delivers commits onto another agent's branch, so the job is finished only when that PR merges. To check, `git fetch` the project's working copy and run `git merge-base --is-ancestor <commit> origin/main` for each commit the job names. A folded commit keeps its hash, so the test is exact. A job whose only artifact is a REPLY (a "no change" read, a launch check, a persona) closes on that REPLY. `fabric-jobs done <id>` takes no note; for work with nothing to name, use `--no-artifact "<what>"`.

**Why:** fabric-coordinator's sweep of 2026-10-18 (REQUEST 01a15091) listed only jobs whose PR had merged. The gzapp#1119 jobs (j38, j42-j46) had commits still off main and stayed open. Closing them would have lost track of copy that can still change in review.

**How to apply:** close by ancestry, keep the rest, and say in the REPLY which PR each kept job waits on. Related: [[name-the-pushed-commit]].

*References: name-the-pushed-commit*

*Observed 2026-10-18 (language-culture)*
