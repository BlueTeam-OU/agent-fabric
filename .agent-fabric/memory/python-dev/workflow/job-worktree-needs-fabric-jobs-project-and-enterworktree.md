---
role: "python-dev"
class: workflow
topic: "job-worktree-needs-fabric-jobs-project-and-enterworktree"
description: "committing in a worktree under a job — the hook wants job working copy = cwd; re-point with fabric-jobs project, then EnterWorktree"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9d312a74965c92c8
---

## committing in a worktree under a job — the hook wants job working copy = cwd; re-point with fabric-jobs project, then EnterWorktree

The PreToolUse commit hook (ADR-037 rule 3) compares the job's recorded working copy with the Bash cwd. A job started in `~/projects/agent-fabric` with its code in a worktree refuses every `git commit`. Fix: `fabric-jobs project <id> <project> --working-copy <worktree>` (allowed until the job has a branch), then the EnterWorktree tool with that path so the shell cwd is the worktree; after that, `git -C`, `env -i` and `<(...)` compounds are refused as "too complex", so run plain separate commands. A job moved to delivered refuses `fabric-pr post-review`: `fabric-jobs start <id>` again.

**Why:** lost ~10 calls in j71 on this. **How to apply:** do both steps before the first commit of a worktree job.

Also (j71): `session.current()` gives kind "detached" to any watch with no claude ancestor hanging from systemd, and two such watches compare equal, so a same-session check must refuse "detached" ([[mutation-run-read-rc-not-fail-count]]).

*References: mutation-run-read-rc-not-fail-count*

*Anchors: `tools/fabric/gzcoord/inbox_parts/session.py::detached`*

*Observed 2026-10-27 (python-dev)*
