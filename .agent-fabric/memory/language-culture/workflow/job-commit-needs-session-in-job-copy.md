---
role: "language-culture"
class: workflow
topic: "job-commit-needs-session-in-job-copy"
description: "a job's commit from a session standing in agent-fabric is refused by the hook; fabric-fresh --job only with a CLEAN job copy, else the launcher starts in agent-fabric again"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 416d0193dab06ed5
---

## a job's commit from a session standing in agent-fabric is refused by the hook; fabric-fresh --job only with a CLEAN job copy, else the launcher starts in agent-fabric again

When the active job is in gzapp and the session was launched in agent-fabric, the PreToolUse hook refuses `git commit` (also via `cd …&&` and `git -C <copy>`): it judges by the session's working copy, not the command's (ADR-037 rule 3). Seen 2026-10-27, j93.

The trap: the launcher refuses to start in the job's copy while it has uncommitted changes (`fabric-fresh --help`) and starts the session in the old directory instead. An edit left staged in gzapp gave three launches in a row in agent-fabric (j93, 2026-10-27).

How to apply: do not edit a job copy's files from a session in another copy. If an edit is already there, `git stash push` it so the copy is clean, note how to restore it, then `fabric-fresh --job <id>`; in the new session, `git stash pop --index`.

*Observed 2026-10-31 (language-culture)*
