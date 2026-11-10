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

### Amendment 2026-10-30 — A fleet hold the job tool enforces

On 2026-10-28 the owner asked for an orderly pause of the fabric: each agent was to finish its current job and then neither start a new one nor unpause one. The fabric had no instrument for that. `fabric-pause` stops sessions instead of letting them finish, and `fabric-jobs switch` always starts the next job. The hold was therefore carried in prose: a broadcast DECISION (01a182e0) told every agent to stop after its active job, and a second DECISION (01a18b15) lifted it on 2026-10-30. Messages are advisory (ADR-024), and a session launched after the broadcast that missed it would have taken its next job. The tool that starts jobs never knew a hold existed. The owner approved a switch on 2026-10-28, the day the hold was set.

Rule 13 puts the hold where jobs start. The control plane sets it on each account, because that is the operator's path to every login and it already carries signed actions such as `jobs-add`. The control agent writes the hold into the login's own state, so `switch` reads a local file and needs no network. A held `switch` still settles the job being left: getting each agent to a settled job is the purpose of the hold, and refusing the whole switch would leave that job unsettled. A hold still queues new work, so a REQUEST that arrives during it is not lost and is answered as held.

Rejected: one fleet-wide hold kept by the coordinator's control agent and queried on every `switch`, as the role pool is (rule 9). An unreachable coordinator would then force a choice between failing open, which loses the hold, and failing closed, which holds the whole fleet when nobody set a hold. A per-account file has neither problem. Its cost, an account missed while its control agent was down, is reported by `fabric-ctl` and fixed by setting the hold again.

### Amendment 2026-10-30 — While held, every start refuses

Rule 13 as first written named only the starts of a queued, paused or blocked job. python-dev-02 built it that way in #431 and reported two paths still open while a hold is set (REPLY 01a18d6e, point 1): `fabric-jobs start` of a delivered job, and `fabric-jobs import` of a list holding an active job.

`start` on a delivered job reopens work the agent had handed off and makes it the active job. That is a new job taken during the hold, and the hold exists to stop exactly that. So every `start` refuses while held, whatever the job's state. The rule now says "any job" instead of listing states, so a state added later is covered without another amendment.

`import` stays allowed. It fills an empty list only, keeping every id, and it moves a login's list from one placement to another. A job that arrives active was taken before the move and is not chosen again by it. Refusing the import would leave the login with no list at all, and that loses more than the hold protects.

### Amendment 2026-10-31 — A clock blocker

On 2026-10-30 a job of the coordinator waited on a time: InterWeave's rollback drill at 17:00Z (j401). No blocker form named a time. `switch` refuses a job blocked on free text, and `pause` is undone by the next `switch`, so the job could be parked neither way, and the session waited on it for about twelve hours (j459).

`clock:<YYYY-MM-DDTHH:MM[:SS]Z>` is the fourth checkable blocker. It is UTC with the trailing Z, because an offset or a local time would read differently on another host; `block` refuses one already past, since a time gone by is no wait. It reads nothing but the clock, so it is never unknown and is evaluated on every look, `--stored` and `--cached` included: the ten-minute re-check would otherwise delay a job past its time, and the control plane would see it clear late. An imported job may carry a past one, and it reads cleared. python-dev-04 built it in #439 (its j76); this note follows the merge.

### Amendment 2026-10-31 — Cleaning a left job's targets is built

Rule 10 step 1 still said that removing the left job's cargo targets was decided and not yet built, and told the agent to remove them by hand. python-dev-03 built it in #350 (its j75), merged on 2026-10-21, the day the step was decided: `fabric-jobs switch` and `next` call `clean_targets` (tools/fabric/jobsparts/leave_targets.py, whose docstring is the contract) once the old job is settled, and `--keep-targets` skips it. The review of #429 (round 1) found the stale sentence. The rule now reads as built and drops the by-hand fallback; nothing it decides changes.

### Amendment 2026-10-31 — In place only from inside the job's copy

On 2026-10-26 backend-dev-02 reported (OBSERVATION, relay seq 574769) a session that `fabric-jobs switch` told to "continue here" and that then could commit nothing. The session had worked no job, so rule 3 took the job in place; it stood in another checkout than the job's, so the job copy guard (A 2026-10-20) refused every commit it tried. The two halves of rule 3 disagreed: the first asked only whether the session had worked a job, the second where it stands. The guard is right. A session in another directory acts on another tree, and changing directory inside a session does not move the hooks, settings and instruction files it was launched with. On 2026-10-31 python-dev-01 (OBSERVATION 01a18f90) found the agent-jobs skill still saying "continue here" without the condition, read on origin/main.

`switch` now asks the guard's own question before it answers in place. It reads where the session stands, as the guard does: the real path of the directory's git toplevel, or the directory itself outside a checkout. It answers in place only when that is the job's working copy or worktree, or under one. Standing elsewhere it answers fresh with the reason `outside_copy`, naming the place and the copies. Where it cannot tell (git silent, the directory gone) it answers fresh with `place_unreadable`. A wrong fresh costs one launch; a wrong in-place leaves a session that cannot commit. A job that records neither copy keeps the in-place answer, since the guard asks there rather than refuses. python-dev-01 built it in #438 (its j194, REQUEST 01a18e24).

Rejected: having `switch` change into the job's copy and continue. The session's cwd belongs to the harness, and a session moved into another copy keeps the hooks and instructions of the one it was launched in, which is why the guard reads the session's own place.

### Amendment 2026-11-05 — An answered request waits on the job it became

Rule 8 cleared a `request:` blocker on any inbound message whose IN-REPLY-TO named the request. The commonest answer to a REQUEST is "taken": the receiver queues it as a job (rule 11) and says so in a REPLY. The REPLY answers the request but delivers no work, yet the blocker cleared, the job read "blocker cleared", was listed first and was taken first by `next`, and the session found nothing to work on. It happened to three of the coordinator's jobs (j349, j412, j526); each time the session had to find the job the request had become and block again on it by hand (j618).

The answerer's own board is the authority on what the request became. Rule 11 titles a delivered REQUEST's job with `(REQUEST <message-id>)`, so the row is found without reading the REPLY's prose. Only without that row is the body read, and only one job of the answerer may be named: two or more are ambiguous, and a token naming someone else's job is not the answerer's. A named job is taken when the answerer's readable board lists it, or when the board cannot be read. When the board is readable and does not list it, the job is closed or was never the answerer's, and the wait is over. The blocker is replaced under the list's lock by `job:<login>/j<n>`, which then clears by rule 8's `job:` test, and the listings say once that the request was answered and what the job now waits on.

A decline, or a DECISION, still clears: a DECISION settles the question and is not a job taken, so its body is not read for one, though a board row for the request still re-points it. When the board cannot be read and the body names no job, the blocker is unknown, never cleared. A "taken" cannot be told from a "no" then, and a wrong clear hands the job back with nothing delivered, which is the failure this amendment exists to stop. python-dev-01 built it in #491 (its j205, REQUEST 01a1aaba).

Rejected: parsing the REPLY's prose for "taken" or "declined". Rule 5 already says the intake cannot tell an undertaking from prose, and the board says it without guessing.

### Amendment 2026-11-08 — One transition table for a job

An external architecture review the owner commissioned (2026-11-08, j674) found that a job's lifecycle is implemented in several places, each keeping part of the rule: `fabric-jobs`' verbs (tools/fabric/jobsparts/verbs.py), `switch`'s settlement (settle.py), the hourly sweep (sweep.py), the inbox intake (gzcoord/intake.py), the control plane's `jobs-add` and the role pool (control/pool.py). Thirteen rules described states and their tests one by one; none said which changes exist at all. Reading the verbs against them shows why that matters: `block` and `deliver` run from any open state, and `done` records the state without its evidence, which only `switch` and `sweep` check afterwards, so a job can read `done` with nothing landed until the next switch. What does hold everywhere is the one guard `records.transition` keeps: a closed job is never reopened (since 8fedfb16, pinned in tests/test_jobs.py).

Rule 14 is one table. Each row is a transition, the one subsystem that may make it, and what must be true when it is made rather than at some later look. `done` and `dropped` are terminal. Edits that change no state (the drain's retitle, a rename, `prio`, `retract`, evidence added to a closed job) are not transitions and stay where they are. The review of #511 found three makers the first draft missed, each now a row: `switch` blocks a job on an unmerged pull request (rule 10 step 3), the claimant's own `pool-claim` writes the claimed job onto its list (the draft credited that half to the pool holder, which writes only `claimed`), and `import` writes jobs in any state into an empty list (rule 13). The plan's working names map onto the existing states: "claimed" is a pool claim landing as `queued`, "working" is `active`, "reconciled" is `sweep`'s `delivered` to `done`; no new state is added, so `jobs.json` and `pool.json` keep their format.

The table is the specification, not yet the code. python-dev-04 pins today's behaviour against it in tests (its j100, REQUEST 01a1bce2), and each disagreement is a finding in that pull request, fixed afterwards and never in the characterisation. A single module that makes every transition, with a checker refusing a state write anywhere else, is the next step and gets its own decision.

Rejected: new state names for the plan's stages (`claimed`, `working`, `reconciled`). They would change the on-disk format and every reader for no new distinction; the existing seven states and the pool's two already carry them.

### Amendment 2026-11-09 — A pool claim ends

python-dev-04's characterisation of rule 14 (#512, its j100, finding F9) found that the table had no row for the pool's own end. `control/pool.py` writes a job `claimed` and never rewrites it: whatever becomes of the claimant's job, the pool shows it claimed for ever, and a claim whose answer was lost is held by nobody, since the claimant's list never queued it. That needs a rule, not a fix of code against one.

Two rows, both made by the pool holder's control agent, which is the pool's only writer (rule 9), and both read from the claimant's state record, fresh within the stream's bound, since the holder never reads another account's list. A claim is `closed` once that record reports the job it became `done` or `dropped`. The pool keeps the claim with when and how it closed, because the pool is also the history of what a role was offered. A claim is `open` again when, a day or more after it was claimed, the record reports the claimant's claims and holds none for this one: the answer was lost, or the job never queued, and the work is offered again.

A record that is missing, stale, unreadable or silent about claims is unknown, and nothing is reopened on it. A claimant whose control agent is down still holds its job, and handing that job to a second claimant would break rule 9's one claimant. The review of #515 (round 1, F1) found that the first wording left this undefined. It also found that the state record carries no claims at all: the control wire's envelope is frozen at the session fields and the optional extras `tools/fabric/control/protocol.py` lists (role, project, last_session, resumable, waits_on). The claims field is therefore part of the rows' build: an optional field added with the job module of Wave 2. Until it exists, neither row is made and a claim stays `claimed`, as today.

A lost answer needs no row. `pool.py` already gives a claim back to the same claimant whenever it claims again (`pool_claim`), so the claimant recovers by asking again. The first wording credited that to rule 9 and bounded it by the day; neither was so (#515 F2).

A closed claim is never handed out again, which the closed row requires of the build. Today's `pool_claim` returns any claim to its claimant (`control/pool.py`, the `claimed.by` check), with no closed state to tell apart. Wave 2's closed shape changes that check, with a test that a closed claim refuses a `pool-claim`, its claimant's included, so finished work cannot become a second job (#515 rounds 2 and 3).

Rejected: removing a closed claim from the pool, since a record that disappears cannot be told from one never made. Also rejected: reopening on the claimant's silence alone, for the reason above.

Decided, not built: the claims field and both rows are implemented with the single module for job transitions of Wave 2 (ADR-067, j674's plan).

### Amendment 2026-11-09 — A peer's job is read by its waiter

Found live on 2026-11-09, between devex-tooling's j306 and rust-ui-dev-02's j95 on InterWeave. Rule 8 read a peer's board through `fabric-ctl <login> jobs`, which is the operator's op alone (control/jobs.py: peers see each other's presence, not each other's lists). For every other login, a `job:<login>/j<n>` blocker was therefore unknown for ever, and an answered `request:` blocker fell back to the job ids named in the REPLY's body. The fallback chose j95, rust-ui-dev-02's long-message job, which was itself blocked on j306, when the request had actually become their j103. Neither side could clear the resulting cycle, and the coordinator cleared it by hand with a clock blocker.

The public `job-state` op (python-dev-03's j122, #527, REQUEST 01a1c038-f234) answers one question for one job: its state, asked by id or by the request whose `(REQUEST <id>)` title it carries. It answers only the job's `source.from`, the sender of the request the job was taken from, and it carries no title, list or other job, so the privacy of a list stays as rule 6 left it. A state or `absent` counts as the board's row did. A refusal counts as a board not read: a `job:` blocker stays unknown, and a `request:` blocker reads the body as before. The board stays the operator's read, and it is also the fallback when the op cannot be asked at all.

The request also allowed a second reader: a login that names the job in its own blocker. It is not built. A blocker lives only in the waiter's own list, which the answering account never reads, so the check would be a claim the asker makes about itself.

A re-point onto a job that waits on one of this login's jobs holding the same request is refused, said, and never stored. That is the cycle seen above. It is seen where this login can read the wait: its own list, or a board it reads as operator. `job-state` carries no blockers, so a cycle through a peer's list that only the peer can read is left for the peer to find from the blocker it holds.

Rule 14 gains no row: a re-point edits a blocked job's blocker and leaves the job `blocked`, so it is listed among the field edits that are no transition.

Rejected: making `jobs` public to the sender of any request on the list. That would show a whole list for the sake of one row, when the waiter needs one state.

### Amendment 2026-11-10 — A landed branch, and a merge before deliver

Seen on the coordinator's j693 on 2026-11-09 and filed as its j710. The job was blocked on its own pull request, the pull request merged, and `switch` then refused the job for three reasons at once. Its recorded branch had landed, so `switch` would not resume on it. `--repoint` applies only to a paused job. `pause` applies only to an active job. Rule 10 step 3 already says what the job is: what it waited on is on the default branch, so it has no branch of its own and takes the agent's open pull request or a new branch. The code had read "a landed branch" as "the job is done", and had no exit for a blocked job. The same reading refused the second case of REQUEST 01a1c27b: a pull request that merged before `deliver` ran is refused by `deliver` (done, not delivered), and `done` could not name it.

Both were fixed by python-dev-03's j125, #541. `switch` treats a blocked job whose recorded branch a pull request merged as a job with no branch, and replaces the landed name in the record. A paused or active job's landed branch is refused as before, because that branch is work in hand. `--repoint` on a blocked job is still refused. `fabric-jobs done <id> <artifact>...` records the named artifacts with the close and takes them as the evidence. Each name is judged on its own, because the `done` test passes a job when any one artifact landed and would otherwise record a closed pull request beside a merged one. A name on a job already done is refused, since `deliver` is what records evidence on a closed job (#541, review round 1).

Rule 14 gains no row. The blocked-to-active change is the existing `switch` row, whose "a branch chosen" now includes this case, and `done` takes its existing row with the named artifacts as evidence.

Rejected: making `--repoint` accept a blocked job. Repoint moves a paused job's work in hand onto an open pull request, and a blocked job whose branch landed has no work in hand to move.
