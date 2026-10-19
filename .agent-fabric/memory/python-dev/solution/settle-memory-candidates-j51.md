---
role: "python-dev"
class: solution
topic: "settle-memory-candidates-j51"
description: "settle.py memory_changed candidates (#275): what counts, the git-failure and gone-worktree traps, and the PR arming facts seen on 2026-10-16"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4d7a742caab49ee1
---

## settle.py memory_changed candidates (#275): what counts, the git-failure and gone-worktree traps, and the PR arming facts seen on 2026-10-16

`tools/fabric/jobsparts/settle.py` `memory_changed` (agent-fabric #275, j51/j52) reads the Claude memory key of each working copy, its repository's main checkout (from `.git`), and the ancestors of both strictly below home; never the home's key; a job with topic `reflection` also counts every `~/.claude/projects/*/memory`. The refusal lists the paths tried.

Traps found by review: (1) `vcs.toplevel` returns None for any git failure, so "is a repository" is read from a `.git` on the path and a later git failure is a note ("could not tell whether the job wrote a memory"), not "unwritten"; (2) a swept worktree under a dir holding `.git` must return None before the probe (`isdir`); (3) a negative test whose message-substring never occurs in the branch it reaches is vacuous: plant the mutation and see it fail (mine asserted "could not tell" where the text said "git could not").

**Why:** a session launched in ~/projects keeps memory under `-home-<login>-projects`; the check used to refuse forever.
**How to apply:** `fabric-pr arm --dry-run` prints the real count rule (here "1 or more work commits arms at the review gate"), not the remit's 8. A push to an armed PR drops the arming (gate: armed=no) and a fold of origin/main changes the head, so it needs a review of the new head and a re-arm; fold-conflict shows as `wait-merged` exit 5.

*Anchors: `tools/fabric/jobsparts/settle.py::memory_candidates`, `tools/fabric/jobsparts/settle.py::main_worktree`*

*Observed 2026-10-16 (python-dev)*
