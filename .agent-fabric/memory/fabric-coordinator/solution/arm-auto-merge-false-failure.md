---
role: "fabric-coordinator"
class: solution
topic: "arm-auto-merge-false-failure"
description: "fabric-pr arm on a PR whose checks are all done: gh pr merge --auto 'fails' while GitHub merges anyway; PR reads stay stale (OPEN, 'merge already in progress', 'not mergeable', wait-merged 'nothing will merge it') — trust origin/main, not…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - aaf23fb0cccb08e9
---

## fabric-pr arm on a PR whose checks are all done: gh pr merge --auto 'fails' while GitHub merges anyway; PR reads stay stale (OPEN, 'merge already in progress', 'not mergeable', wait-merged 'nothing will merge it') — trust origin/main, not the PR API

2026-10-13, #237: CI green and both reviews on the head, so the PR was CLEAN. `fabric-pr arm` ran
`gh pr merge --merge --auto --match-head-commit`, which exited non-zero ("failed on #237"). GitHub
had merged it anyway: origin/main got the merge commit f12fe1fc at 15:06:49, while for minutes the PR
API said state OPEN, then "Merge already in progress", then mergeable CONFLICTING/DIRTY (the head
already in main), and `fabric-pr wait-merged` said "neither queued nor auto-merge-armed — nothing will
merge it". The owner: a pattern seen before (cf. [[arm-failure-no-hand-merge]], 2026-10-10).

**Why:** enabling auto-merge on a PR with nothing left to wait for makes GitHub merge at once, and the
call can report an error; the PR's own fields lag the merge.
**How to apply:** after an arm "fails", first `git fetch` and check whether the head is in
origin/main (`git merge-base --is-ancestor <head> origin/main`) before any retry; never merge by hand
on a stale "OPEN". The fix belongs in arm.py and wait-merged (devex-tooling's): read origin/main after a
failed merge call, and merge without --auto when the PR is already CLEAN.

*References: arm-failure-no-hand-merge*

*Observed 2026-10-13 (fabric-coordinator)*
