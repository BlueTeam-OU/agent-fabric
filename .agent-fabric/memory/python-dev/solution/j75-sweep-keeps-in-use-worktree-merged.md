---
role: "python-dev"
class: solution
topic: "j75-sweep-keeps-in-use-worktree-merged"
description: "j75 PR #349 merged — fabric-branches --sweep keeps a worktree a process stands in or a fabric-in-use pid names; traps found"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ae948cddb47b4bb5
---

## j75 PR #349 merged — fabric-branches --sweep keeps a worktree a process stands in or a fabric-in-use pid names; traps found

#349 (4 work, 1 fix) merged 2026-10-21. `worktree_state` appends `in use: <reason>` from `in_use_by`: a /proc scan of this uid's cwds (at or under the worktree), else `fabric-in-use` in the worktree's own git dir (`rev-parse --absolute-git-dir`), first line a live pid of this uid. The writer is review_brief.py on the coordinator's j323 branch (c27b9b65).

**Why:** the first marker design put the file in the tree; it was untracked, so git called it a change and `git worktree remove` refused with it present. The coordinator moved it to the git dir, which needs no filter and no unlink.

**How to apply:** open a same-uid-writable marker with O_NOFOLLOW|O_NONBLOCK and fstat the descriptor (lstat-then-open lets a FIFO hang the sweep); liveness via /proc/<pid> owner, not kill(2); an unlistable /proc keeps worktrees. Unverified: another uid's process, non-dumpable processes (root-owned /proc entry), own pid namespace. Under load ~85 the full suite flakes (gzcoord protocol 10 s subprocess timeout, test_session_start job-list case); both pass alone.

*Anchors: `tools/fabric/branches.py::in_use_by`, `tools/fabric/branches.py::marker_pid`*

*Observed 2026-10-21 (python-dev)*
