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

### Amendment 2026-09-30 — The opening prompt names no command

The opening prompt stays in the claude process's argv for the whole
session, and it named `gzcoord-inbox --follow`. A session tidying
"stale" watchers with `pgrep -f 'gzcoord-inbox --follow' | xargs kill`
matched its own claude process and killed itself: architect-cto-01,
twice on 2026-09-29, which the owner first took for a failed restart.
The prompt now tells the session to arm the watch as the start hook's
NO INBOX WATCH line gives it (context, never argv), or as the
gzcoord-receive skill says where the context has none, and names no
command. `runtime/claude-code/hooks/self-kill-guard.py` refuses a kill
whose pattern matches the session's own command line; `fabric-fresh`,
which signals by pid, is unaffected.

### Amendment 2026-10-10 — The watch is a background command, not a Monitor

The watch ran as a Monitor on `gzcoord-inbox --follow`. The harness caps
a Monitor at 30 minutes, so every quiet session got an expiry notice
every half hour, which rang the Fleet Deck's sound and woke the agent to
re-arm: annoying and costly (the owner). The watch is now
`gzcoord-inbox --until-delivery` run as a background Bash command
(`run_in_background`, `timeout: 7200000`): it blocks quietly, exits on
the first delivery addressed to the session, and the harness wakes the
session once per delivery; the session reads the output and runs it
again. A quiet session is woken at most once per two hours, the Bash
timeout. A refused token ends it with exit 4 and a relay unreachable for
fifteen minutes with exit 5, the reason on stdout. `--follow` is
unchanged for other consumers, and the start hook recognises either under
the session. §2 and §5 rules 1, 2 and 6 name the new command; the
launcher's opening prompt says to run it again after each delivery.

### Amendment 2026-10-11 — Every job starts in a fresh session

The owner decided on 2026-10-11 that an agent starts a fresh session for every job it takes after finishing one; keeping the prompt cache warm is not a reason to continue. A fresh launch reads the fabric anew (launch prompt, charter, CLAUDE.md, hooks), which the fleet upgrade updates on disk and a running session never re-reads, so a continued session works on stale rules. `fabric-jobs next` therefore no longer compares project, working copy and topic: a session that has already worked a job gets `fabric-fresh --job <id>` always; a session that has worked none (just launched) takes the job in place, being already fresh. A job's `active` log entry records the harness session id (`CLAUDE_CODE_SESSION_ID`), which is how a session is told to have worked a job; an active job is still never preempted and a blocked one is still taken only by name.

### Amendment 2026-10-19 — Stale worktrees and ended sessions' scratch are swept

§5 rule 11. The owner, 2026-10-19: "you should tell also agents to do
clean out of old stale things". One login alone held 39 leftover
worktrees that day (review heads, drains, job checkouts across ten
repositories, about 530 MB), none of which the sweep could remove: it
took only worktrees whose commit was on the default branch, so pushed
but unmerged work and detached review heads stayed. Two agents asked to
clear their own ended sessions' scratch by hand were refused by the
auto-mode classifier, which is why that is a command and not an rm
rule. A worktree whose HEAD is on a branch the remote still has
loses nothing when removed: its commits stay on the remote. The proof
is `git ls-remote`, not the local remote-tracking ref, which a fetch
without prune keeps after the host deleted the branch; and liveness is
the harness's own session registry, since its process does not carry
its session id in its environment (both found by the review of #330). The sweep now removes
those, covers every working copy with `--all`, removes ended sessions'
scratch, and runs its worktree half when a job ends.

### Amendment 2026-10-20 — An unreadable session registry keeps every worktree

python-dev-03 built it in #337 (merged 2026-10-20). The rule had a
registry that cannot be read keep all the scratch but leave the worktree
half to `AGENT_FABRIC_BRANCHES_KEEP` alone, so a live session's worktree
the variable did not name could be removed under it. Now nothing the
registry would have judged is removed: each worktree is kept and listed
as "session registry unreadable", branch deletion is unchanged, and
`fabric-branches --json` reads the registry too, so the control plane's
removable count agrees with the sweep. A readable registry that lists no
one still lets a worktree go.
