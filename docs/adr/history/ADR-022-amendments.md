# ADR-022 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-28 — An agent ends its own job with a fresh session

The owner, to the fabric-coordinator session, after asking how the
control plane could force a /clear on a session: "what i wish is that at
the end of a task/job a agent can do this on himself", then "put in the
same open pr".

A slash command comes only from the person at the keyboard, so a model
cannot /clear itself. The session is the launcher's child, though, and
the launcher already relaunches after a restart marker (the fleet
upgrades of ADR-009), resuming the stopped conversation. `fabric-fresh`
writes that marker with `fresh` true and a note and stops its own
session; the launcher, on a fresh marker, relaunches with no `--resume`
and puts the note in the opening prompt. The finished conversation stays
on disk. The command is refused outside a launched session (nothing
would bring one back) and on uncommitted changes unless `--force` (a job
not yet at its artifact). When to use it is the agent's judgement,
stated in CLAUDE.md; the owner's two choices, a refusal rather than a
warning on uncommitted changes and guidance rather than a rule on every
job, were taken as the safer defaults.

### Amendment 2026-09-28 — Local branches are swept weekly

The owner gave the fabric-coordinator session a branch-hygiene prompt,
"a process that each agent should do periodically": orient, a plain
fetch, every local branch counted against origin/main, worktrees and
their changes, a report, then the deletion of what shows 0, re-checked,
local only. Asked when and how, the owner chose a weekly nudge only (not
a step at the end of every job) and "delete 0s alone, ask for the rest".

`fabric-branches` carries the procedure so it is not redone from prose:
the report deletes nothing; `--sweep` refuses uncommitted changes and a
failed fetch, deletes the branches at 0 and removes clean worktrees at
0, keeps and lists everything else with its commits and pull request,
and records the sweep per working copy. The session-start hook reads
that record and says when it is over seven days old, in keeping with a
pull-based fabric. A merged pull request whose commits still count
above 0 (squashed, or history rewritten) is reported, never deleted:
the count cannot prove it merged.

### Amendment 2026-09-28 — The next job decides whether the session continues

Rule 10 left the moment of a fresh session to the agent's judgement, and
its relaunch always reopened the launcher's own directory. The owner
asked for a restart when the next job is in another repository, or on a
subject that is basically different, and chose that the command decides
and the agent confirms. Rule 12 is that rule: `fabric-jobs next` compares
project, working copy and topic (a label the agent sets) and prints
`fabric-fresh --job <id>` on any difference; the launcher starts the new
session in the job's working copy, with the job in its opening prompt,
and refuses a working copy that is gone or dirty by starting where it
was. The job list itself is ADR-037.
