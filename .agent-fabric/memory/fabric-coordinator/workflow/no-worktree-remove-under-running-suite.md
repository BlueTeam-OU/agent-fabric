---
role: "fabric-coordinator"
class: workflow
topic: "no-worktree-remove-under-running-suite"
description: "Before removing a merged PR's worktree, stop or wait for every background run started in it; TaskStop leaves run.py's children alive"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - eb93f5678559f372
---

## Before removing a merged PR's worktree, stop or wait for every background run started in it; TaskStop leaves run.py's children alive

2026-10-20, #332 merged while my local full suite still ran in its worktree. `git worktree
remove` half-failed ("Directory not empty", the worktree deregistered, 25 MB left), and after
TaskStop the suite's children (bash, tests/run.py, run_python_suites.py) were still running
in a directory that no longer existed.

**Why:** a background task started with `cd <worktree> && tests/run.sh` keeps writing there;
TaskStop ends the shell, not its process tree.
**How to apply:** before removing a worktree, check the session's background tasks for one
whose command names it; let it finish or TaskStop it, then confirm by pid that nothing of it
runs (`ps -o pid=,args= -p <pids>`; a kill by exact pid, never in the same command as a
pgrep, which the self-kill guard refuses). Then `git worktree remove`.

*Anchors: `tests/run.py::run_python_suites`*

*Observed 2026-10-20 (fabric-coordinator)*
