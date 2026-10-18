---
role: "p2p-network-dev"
class: workflow
topic: "fabric-jobs-add-takes-project-from-cwd"
description: "fabric-jobs add records the project of the working directory it runs in; run it from the project's working copy, or switch makes the worktree in the wrong repository"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0c95c3b3257f2fbb
---

## fabric-jobs add records the project of the working directory it runs in; run it from the project's working copy, or switch makes the worktree in the wrong repository

`fabric-jobs add` records the project and the working copy of the directory it runs in. It does
not look at the job title.

On 2026-10-16 an InterWeave job (j74) was added from agent-fabric/. `fabric-jobs switch` then
created its branch and worktree off agent-fabric's origin/main. The fix was to drop the job, remove
the empty worktree, and add it again from interweave/ (as j75). j73 carries the same mislabel.

**Why:** a fresh session for that job starts in the wrong repository.

**How to apply:** `cd` into the project's working copy in the same command as
`fabric-jobs add`. A Bash call resets the cwd to the session's start directory, which is
agent-fabric here.

*Anchors: `tools/fabric/control/jobs.py::add`*

*Observed 2026-10-16 (p2p-network-dev)*
