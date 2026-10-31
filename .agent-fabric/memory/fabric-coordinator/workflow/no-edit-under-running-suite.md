---
role: "fabric-coordinator"
class: workflow
topic: "no-edit-under-running-suite"
description: "A running tests/run.sh reads the worktree's live files; no stash, checkout or edit there until it ends, or its verdict proves nothing"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 009e200f4ab4587f
---

## A running tests/run.sh reads the worktree's live files; no stash, checkout or edit there until it ends, or its verdict proves nothing

2026-10-24, #361: I ran `git stash` in the j341 worktree, to get a before/after control for a new test, while a background `tests/run.sh python` ran in that same worktree. The suite then read a mix of stashed and unstashed files, so its one failure (a timing check under load 33) could not be trusted. I had to rerun it. The stash also made the control meaningless, because it removed the new test along with the fix.

**Why:** the suites run the checkout as it is on disk, file by file, over many minutes. Anything that changes files there mid-run changes what they test.

**How to apply:** while a suite runs in a worktree, edit and commit nowhere in it. Run a before/after control in a separate detached worktree (`git worktree add --detach ~/agent-fabric-tmp/<x> HEAD`, copy the new test in, run it, then `git worktree remove --force`). That shows the test fails without the fix. Related: [[no-worktree-remove-under-running-suite]], [[suite-snapshots-git-config]], [[checks-need-a-control]].

*References: checks-need-a-control, no-worktree-remove-under-running-suite, suite-snapshots-git-config*

*Anchors: `tests/run.sh::FAILED_SUITES=`*

*Observed 2026-10-24 (fabric-coordinator)*
