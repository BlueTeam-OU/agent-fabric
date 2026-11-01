---
role: "fabric-coordinator"
class: solution
topic: "guard-counts-session-cwd"
description: "Why a session standing outside its job's copy cannot commit at all — git -C and cd && are denied too"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5c973e341866ac53
---

## Why a session standing outside its job's copy cannot commit at all — git -C and cd && are denied too

The job copy guard (runtime/claude-code/hooks/job-copy-guard.py) always counts the PreToolUse payload's cwd as a directory the command acts in. So from a cwd outside job J's working_copy/worktree, `git -C <worktree> commit` and `cd <worktree> && git commit` are denied just like a plain commit. Verified 2026-10-30 with a scratch fixture (tests/jobs_world.py) on e6a89e72 and on #432@6466db3f. The fix is not to move the session (the harness resets a shell cwd outside the primary directory). Get a fresh session that launches in the copy. j410 contracted that to python-dev-01 (REQUEST 01a18e24): switch should give fresh, not "continue here", when the cwd is outside. After #432 the recorded working_copy is the worktree, so the main checkout counts as outside too.

**Why:** a session that switched in place from the wrong directory was stuck, with every commit denied (backend-dev-02, 2026-10-26).
**How to apply:** when an in-place switch leaves me outside the job's copy, run fabric-fresh --job instead of trying to rephrase the commit. Related: [[job-in-other-repo-needs-fresh-session]].

*References: job-in-other-repo-needs-fresh-session*

*Anchors: `runtime/claude-code/hooks/job-copy-guard.py::THE DIRECTORIES A COMMAND ACTS IN`*

*Observed 2026-10-30 (fabric-coordinator)*
