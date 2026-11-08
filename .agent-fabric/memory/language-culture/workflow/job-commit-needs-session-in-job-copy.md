---
role: "language-culture"
class: workflow
topic: "job-commit-needs-session-in-job-copy"
description: "a job's commit from a session standing in agent-fabric is refused by the hook; fabric-fresh --job only with a CLEAN job copy, else the launcher starts in agent-fabric again"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 291e44ff61a7413a
  - 416d0193dab06ed5
---

## a job's commit from a session standing in agent-fabric is refused by the hook; fabric-fresh --job only with a CLEAN job copy, else the launcher starts in agent-fabric again

When the active job is in gzapp and the session was launched in agent-fabric, the PreToolUse hook refuses `git commit` (also via `cd …&&` and `git -C <copy>`): it judges by the session's working copy, not the command's (ADR-037 rule 3). Seen 2026-10-27, j93.

The trap: the launcher refuses to start in the job's copy while it has uncommitted changes (`fabric-fresh --help`) and starts the session in the old directory instead. An edit left staged in gzapp gave three launches in a row in agent-fabric (j93, 2026-10-27).

Since #438 (00616fdf, on main from 2026-11-01) `fabric-jobs switch` no longer tells a session outside the job's copy to continue in place: it answers fresh (outside_copy) and prints the `fabric-fresh`. That removes one cause of the loop; the launcher's refusal of a dirty copy remains.

How to apply: follow what switch prints. Do not edit a job copy's files from a session in another copy. If an edit is already there, `git stash push -u -m <unique-tag>`, note the entry's SHA (`git stash list --format='%H %gs'`), then `fabric-fresh --job <id>`; in the new session `git stash apply <sha>` (not pop: the stash stack is shared by every copy), then drop the entry, found by its tag.

*Observed 2026-11-01 (language-culture)*
