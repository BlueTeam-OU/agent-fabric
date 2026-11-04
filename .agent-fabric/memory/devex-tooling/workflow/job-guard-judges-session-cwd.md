---
role: "devex-tooling"
class: workflow
topic: "job-guard-judges-session-cwd"
description: "commit refused \"outside the job's working copy\" though cd/git -C named it — the guard reads the session's cwd; relaunch with fabric-fresh --job"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f7715be726110178
---

## commit refused "outside the job's working copy" though cd/git -C named it — the guard reads the session's cwd; relaunch with fabric-fresh --job

The ADR-037 rule 3 PreToolUse guard over-reports the directories a commit acts in: the payload's cwd always counts beside every `cd`/`-C` target, so `cd <wc> &&` or `git -C <wc>` does not clear it: a session started in ~/projects/agent-fabric cannot commit job j209's settings worktree (2026-10-24). The shell cwd resets each call.

**Why:** a session works one job's working copy; the launcher places it there only on `fabric-fresh --job <id>`.
**How to apply:** when session-start says "your active job is in <other dir>", run `fabric-fresh --job <id>` before editing. The launcher refuses a dirty working copy, so do not stage edits there first; verify read-only, then relaunch. See [[settings-repo-job-needs-own-working-copy]].

*References: settings-repo-job-needs-own-working-copy*

*Anchors: `runtime/claude-code/hooks/job-copy-guard.py::THE DIRECTORIES A COMMAND ACTS IN`*

*Observed 2026-10-24 (devex-tooling)*
