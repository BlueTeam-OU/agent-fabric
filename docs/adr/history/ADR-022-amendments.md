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

### Amendment 2026-10-24 — A worktree a live job names is kept

python-dev-04 built it in #364 (merged 2026-10-24, its job j65). A job
records its worktree, and `fabric-jobs switch` and `fabric-fresh --job`
send the next session there; the sweep removed a clean, pushed worktree
whatever named it, so a queued job could be left pointing at a
directory that no longer existed (j64, 2026-10-24). Now a worktree a
queued, active, paused or blocked job of the login names is kept and
listed as "named by job jN (state)"; a delivered, done or dropped job
names nothing. Unknown is not none: a job list that cannot be read, a
record whose worktree is not a path, or a state outside those
`fabric-jobs` writes keeps every worktree, listed as "job list
unreadable", and branch deletion is unchanged (#364 review F1).

### Amendment 2026-10-27 — A fresh launch starts in the job's own dirty working copy

language-culture-ru (OBSERVATION 01a17d7f, j93) looped through three
relaunches: its edit sat staged in the job's gzapp copy while the
session stood in agent-fabric, the job-copy guard (ADR-037 rule 3)
refused the commit from there, and `fabric-fresh --job j93` refused
the dirty gzapp copy and started in agent-fabric again; only a hand
stash broke it. python-dev-03's #407 (j89) lets the launcher start in
the job's own working copy even with uncommitted changes, the job's
work in progress; it still refuses a copy that is gone or whose git
status cannot be read, and a dirty copy that is another unfinished
job's worktree or whose job list cannot be read.
Rule 12 says so.

### Amendment 2026-10-28 — The sweep deletes the login's own merged branches on origin

architect-cto-01 found 256 of InterWeave's 266 origin branches on main
(REQUEST 01a18168-0ae7, 2026-10-28): delete-on-merge removes only a
pull request's own head, so every `for/` supply branch folded into
another lane's PR (234) and every branch folded into one of its own
lane or pushed after the merge (24) stayed. The owner had them pruned
by hand; rule 11 said "local only", so nothing would stop them growing
back. python-dev-03's #416 (j92) makes `fabric-branches --sweep` delete,
on origin, each branch under the login's own `<host>/<login>/` whose
`git ls-remote` tip is an ancestor of the freshly fetched default branch
and that heads no open pull request, with a push leased to that tip so
one pushed since stays. The plain report lists them as the dry run.
Another login's branch, a branch with a commit off the default branch
(a squash-merged one: accepted) and an open PR's head are never
touched; `gh` missing or unauthenticated ends the step with a line,
since an unknown PR state is not none, and the local sweep goes on.
`--sweep --worktrees`, which `fabric-jobs switch` runs, deletes nothing
on origin.

### Amendment 2026-10-30 — A fresh launch starts in the job's worktree; the session carries the verified fabric root

Three sessions of one login ran stale fabric code on 2026-10-30, and
twice the inbox and `gzcoord-send` broke on it (`episodic.db` at schema
3, the code reading it at 2). Two causes. `fabric-fresh --job` relaunched
in the job's `working_copy`, which the record had left on an old
worktree 348 commits behind, while the job's `worktree`, where its branch
lives, was elsewhere. And a session took `AGENT_FABRIC_ROOT` from the
SessionStart hook of the checkout it started in, which defaults to that
checkout: the launcher checked its own root against origin/main and then
did not pass it on, so a session started in a fabric worktree ran that
worktree's code.

python-dev-02's #432 (j102, REQUEST 01a18d9f) makes the fresh relaunch
take the job's worktree before its working copy, with the same checks,
saying which it took when the two differ and falling back to the working
copy, said, when the worktree is gone; `fabric-jobs` now writes
`working_copy` with `worktree` so the two stop drifting. The launcher
writes `AGENT_FABRIC_ROOT=<the root it verified>` into the session's
environment, which `session-start.sh` already honours. A start
directory that is an agent-fabric checkout other than the root, and
behind, is named as having its own hooks and settings. Neither is a
refusal: a feature worktree behind main is ordinary work, and refusing
it would stop the work the warning is about. Rule 12 says so.

