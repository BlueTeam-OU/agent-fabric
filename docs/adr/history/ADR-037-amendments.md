# ADR-037 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-08 — Priority, blocking derived, a role pool, and taking the next job

The owner asked that an agent which closes a job looks for the next and takes it, and that the queue know priority, with a job that blocks another agent first. Asked how, the owner chose: the agent's own list, then a pool for its role; blocking derived from other agents' blocked jobs, beside an explicit priority anyone adding a job may set.

- Rule 7 adds the priority and its order, never preempting the active job and leaving a blocked one in place.
- Rule 8 derives `blocking` from the state stream: the message ids a blocked job waits on, ids only, so rule 6's "not each other's lists" holds.
- Rule 9 adds the role pool, serialized in the coordinator's control agent, with the claim checked against the claimant's own binding.
- Rule 10 is the duty to take the next job.

python-dev-01 builds it (its REQUEST, relay seq 20917, undertaken with two points this text keeps: an effectively blocking job keeps its stored priority, and the claim reads the claimant's binding).

### Amendment 2026-10-09 — A stale waiter still counts

Rule 8 said a queued job others wait on ranks blocking, but not what happens when the waiter's state record is old. #124 settled it in code (python-dev-01, on fabric-coordinator's ruling in its request thread): the waiter still counts, because its block lives in its own `jobs.json` whether or not its control agent is running to report it, and dropping the rank would hide a real wait behind an agentd restart. `fabric-jobs list` names such a waiter with the record's age and says it is stale; `runtime/control/queue.mjs` returns the stale waiters beside the waits. This entry is the record half.

### Amendment 2026-10-09 — A REQUEST to a login is queued on its list

On 2026-10-09 python-dev-03 held three REQUESTs from the coordinator for an hour with an empty job list; the owner pointed at the list, and the jobs, added by hand, were what the session would meet. §7 had kept the intake for later, keyed on an undertaking REPLY; a login that has not yet read a request sends none, so the intake is keyed on delivery instead, and the operator's send adds the job through the existing jobs-add action for a session whose watch has lapsed. No wire changes: a request id on jobs-add waits for ADR-040 §7. The owner approved it the same day, from the reading of "loops, graphs & harnesses" (enforce over document). python-dev-02 builds the tools (REQUEST 01a11f64).

### Amendment 2026-10-09 — A job may be a plan's step

ADR-047 has the coordinator keep plans whose steps are jobs on agents' lists. The link lives in the plan, so no agent's job and no frozen operation changes; a step given at dispatch waits for the wire to allow new arguments.

### Amendment 2026-10-11 — Every job starts in a fresh session

The owner decided on 2026-10-11 that an agent starts a fresh session for every job it takes after finishing one; keeping the prompt cache warm is not a reason to continue. A fresh launch reads the fabric anew (launch prompt, charter, CLAUDE.md, hooks), which the fleet upgrade updates on disk and a running session never re-reads, so a continued session works on stale rules. `fabric-jobs next` therefore no longer compares project, working copy and topic: a session that has already worked a job gets `fabric-fresh --job <id>` always; a session that has worked none (just launched) takes the job in place, being already fresh. A job's `active` log entry records the harness session id (`CLAUDE_CODE_SESSION_ID`), which is how a session is told to have worked a job; an active job is still never preempted and a blocked one is still taken only by name.

### Amendment 2026-10-12 — Checkable blockers

A job blocked on a pull request or a peer's job waited for a person to notice the merge or the delivery. #211 made the wait checkable: `fabric-jobs block <id> --on <blocker>` takes `pr:<owner/repo>#<n>` (cleared when the pull request is merged or closed, read through gh), `request:<message-id>` (cleared when a REPLY whose IN-REPLY-TO is that id is in this login's journal) and `job:<login>/j<n>` (cleared when that job is delivered, or has left the open list after it was seen open, read through fabric-ctl); several may be given and all must clear. `list`, `next` and `block` check a blocker at most once every ten minutes and never again once it cleared (`jobs-blockers.json` in the state directory); a check that cannot be told is `unknown` and never clears. A job whose blockers have all cleared reads "blocker cleared: <what>", is listed first and is what `next` takes before anything queued, so the agent moves it on itself. `--stored` and `--cached` check nothing and read the cache; `list --json` carries `blockers` and `cleared` for such a job. `--on-request` is now the same blocker. The session-start hook reads `list --json --cached` and names the cleared jobs in its jobs line, with no network.

### Amendment 2026-10-14 — Paused, and the transition between jobs

The owner, 2026-10-14: "how an agent move to another job, should be better designed" — first an evaluation of the previous job's status (still open and so paused, blocked and so moving to another, closed and marked as such), then whether the next job needs a fresh session, then opening a branch. The day's evidence for each step: a sweep of the coordinator's list found 41 of 97 open jobs already done; j176 stayed `active` a day after its work merged; j44 stayed `blocked` on a merged pull request; an agent switched away from unfinished work with no state but `blocked` to say so; the coordinator's own branch was 12 commits behind main and failed a suite for that alone; and nothing checked the duties before leaving a job (commit, push, answer, memory). The owner's answers: add `paused`, because "blocked is something the agent doesn't control, paused is something [it] decides to"; keep rule 3's fresh session after every worked job, with no evaluation of the old context; refuse the switch when a check fails. `fabric-jobs next` stands until `switch` is built.

### Amendment 2026-10-15 — Built, and the text says so

The prompt audit of 2026-10-14 (j45) found the record still saying the request intake was "decided and not yet built" and the DIGEST listing `paused` as "unbuilt". Both are built: the inbox queues a delivered REQUEST (`tools/fabric/gzcoord/intake.py`), and `fabric-jobs pause` and `switch` exist (`next` is its alias). `fabric-adr lookup` serves this text to agents, which then added requests by hand and set work aside as `blocked`. The body and the DIGEST entry now read current; no rule changes.

### Amendment 2026-10-16 — A delivered job whose evidence landed is swept to done

The owner, 2026-10-16, reading devex-tooling's tab in the fleet deck, took its job count for open work: it held 67 delivered jobs against 1 active and 3 queued, and the fleet held 387. `switch` reads a delivered job's evidence once, when its agent leaves it; a supplier's work that merged later, inside the caller's pull request, stayed delivered for good. Delivered stays open (a hand-over waits on someone else), and rule 12 makes it mean only that: `fabric-jobs sweep` (#282, python-dev-02) applies `done`'s test again and closes what has landed, and the control agent runs it hourly because a supplier's session may never start again to do it. The deck's count shows delivered apart from active and queued (FleetDeck, rust-ui-dev-02).

### Amendment 2026-10-18 — Work that leaves no artifact closes with a reason

Rule 10's `done` test accepted only a merged pull request or a commit on the default branch, and `drop` refuses a closed job, so a job whose work lands nothing in a repository could be closed but never left: three agents (edge-hosting, rust-services-dev-02, flutter-dev-02) hit it the same day, after a coordinator broadcast asked each to record its disk cleanup as a job. Such work now closes with `fabric-jobs done <id> --no-artifact "<what was done>"`: the reason is required, recorded on the job and shown, and `switch` accepts it as that job's evidence; the same command settles a job already closed done without evidence. A reason never stands in for evidence the job does have: an open pull request or an unfolded branch still refuses (agent-fabric #299).

### Amendment 2026-10-20 — A session works one job's working copy

The owner reported it through architect-cto-01 on 2026-10-20. A session launched for an InterWeave job closed that job and then took a gzapp question that expected a reply. It changed into its gzapp checkout and committed there (gzapp 9fbb51030) without running `fabric-jobs switch`. Its own reasoning named rule 3 and carried on. Prose had not held, so rule 3 gets a fence.

The fence is a PreToolUse hook on Bash. It runs session-side because the fact it needs, which job this session worked, lives in the job log under the harness session id, and CI never sees that. The hook refuses a command that commits or publishes (git commit, push, merge, rebase, cherry-pick or am; a pull request opened or merged) when it acts in a directory outside the session's job copies. When the session's job has left `active`, it refuses every such command.

Reads in other copies stay allowed, because diagnosing anywhere is every role's right. A session with no job is left alone, which covers the owner's own sessions. The hook reads directories by over-reporting: any `cd`, `pushd` or `git -C` target outside the copies, or one it cannot resolve, counts as outside. A false refusal costs a rephrase; a false allowance is the incident.

The inbox path needs no change. Intake already queues a delivered REQUEST as a job (rule 11), and this fence is what stops the session acting on it in place. When the hook cannot read the job list or the tree, it asks rather than allows.

### Amendment 2026-10-21 — Leaving a job cleans its build output

/home on the fleet's host filled twice between 2026-10-20 and 2026-10-21. The first time it reached 98%, and other logins' runs failed with ENOSPC. The second time the owner added 100G. `fabric-ctl all disk` put almost all of it in cargo `target` directories of 60 to 75G each, one per job worktree, left behind after the job moved on. Asked by message, the agents freed about 270G the first time, and three of the directories were back within hours.

The owner approved cleaning on leaving a job: `fabric-jobs switch` is to remove the old job's worktree targets once the job is settled, whatever the outcome. python-dev-03 builds it (its j75); this record was written before the code landed.

One shared target directory per login was proposed and withdrawn before anything was built. InterWeave binaries bake in `CARGO_MANIFEST_DIR`, and cargo does not rebuild for another worktree with the same sources. A shared target therefore runs binaries that point at the first worktree's paths, which failed all of xtask's checks once on 2026-10-07 (rust-ui-dev's slice shared-target-worktree). How large a project's builds are is the project's own decision (InterWeave: architect-cto, asked 2026-10-21).
