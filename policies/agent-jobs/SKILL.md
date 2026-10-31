---
name: agent-jobs
description: "Your own job list: what you have undertaken, are doing, wait on and have delivered, kept with fabric-jobs so it outlives this session; its priorities, a job blocked on another agent's request, your role's open pool, a fleet hold, and the restart rule that says what to take next and when it needs a fresh session. Load it when you take on a piece of work, when the session-start context shows a jobs line, when a job reaches its artifact, or before deciding what to do next."
---

# Your job list

Each login keeps one list of its jobs in its runtime state
(`agents/<login>/jobs.json`). The owner reads it through the control
plane, and a fresh session is started for the job it names. The
conversation is not the record: what is not on the list is lost when the
session ends. `fabric-jobs` is the only way to change it.

## 1. When to add a job

Add a job when you take on a piece of work that ends in an artifact: a
pull request, a reply, a drain, a decision record. Do not add one for a
step inside a job.

```sh
fabric-jobs add "<what the artifact is>" --topic "<short label>"
fabric-jobs add --request <MESSAGE-ID> --topic "<short label>"   # a request you have undertaken
fabric-jobs add "<artifact>" --priority high                      # blocking | high | normal (default) | low
```

- **Title:** the artifact, not the activity ("the drain of the five
  correction memories", not "look at memories").
- **Where:** the job's project and working copy are the directory you
  run it in. Pass `--working-copy` (or `--project`) for work elsewhere.
- **Topic:** a label you choose: "memory drain", "routing", "boarding
  evidence". Two jobs with the same label are one subject. The label is
  how the restart rule knows whether a subject has changed, so reuse a
  label exactly for the same subject.
- **Requests:** a request from another agent becomes a job only when you
  add it. First answer it as always, with a REPLY saying what you
  undertake. Then `add --request` fills the title, the sender and the
  project from the message. It is refused for a message not addressed to
  you, or one already on your list. Nothing adds a request for you.
- **Priority:** `normal` unless you say otherwise. Use `blocking` for a
  job another agent waits on, `high` for one the owner said is urgent,
  `low` for one that can wait behind everything else. Change it later
  with `fabric-jobs prio <id> <priority>`.

## 2. Keep its state true

| When | Run |
|---|---|
| You start on it | `fabric-jobs start <id>` (one job is active at a time) |
| It waits on something you do not control | `fabric-jobs block <id> --on pr:<owner/repo>#<n>` (or `request:`, `job:`), or `"owner: <the decision awaited>"` |
| You set it aside by choice | push its branch, then `fabric-jobs pause <id> "<why>"` |
| It waits on another agent's request being done | `fabric-jobs block <id> --on-request <MESSAGE-ID>` |
| Its artifact exists | `fabric-jobs deliver <id> <pr-or-commit>...` |
| The artifact landed and nothing is owed | `fabric-jobs done <id>` |
| Its work leaves no repository artifact (a cleanup) | `fabric-jobs done <id> --no-artifact "<what was done>"` |
| It will not be done | `fabric-jobs drop <id> "<why>"` |
| An artifact was entered by mistake | `fabric-jobs retract <id> <artifact>`, exactly as `show` lists it; any state, done included |

`fabric-jobs list` shows the open jobs. `fabric-jobs show <id>` shows one
in full.

**Blocked on a request.** When your job waits on work you asked another
agent for, block it with `--on-request` and the id of the REQUEST you
sent. Your control agent then tells the fleet you wait on that message,
and the job it became on the other agent's list ranks `blocking` there,
whatever priority they gave it. A plain-text block tells nobody.

**Ranked blocking for someone else.** `fabric-jobs list` shows a queued
job that another agent waits on as blocking, with the address that
waits. If the state stream cannot be read, the list says so and falls
back to the stored priorities; `--stored` skips the stream.

## 3. What comes next: the restart rule

You move between jobs with `fabric-jobs switch [<id>]` (`next` is its
alias; ADR-037 rule 10). It refuses, saying what to fix, unless the job
you leave is settled with its evidence (done: merged, or a `--no-artifact` reason; delivered: its PR
open; blocked: a named blocker; paused: its branch pushed; dropped: a
reason; a reply-only job: `reply:<MESSAGE-ID>` as its artifact, the id
`gzcoord-send` printed for your answer or the id of the message it
answers; a reflection job: your `fabric-reflect` cursor closed after the
job started), nothing is uncommitted, and every REQUEST or QUESTION
addressed to you with `REPLY-EXPECTED: yes`, received since the earlier
of the job's and the session's start, is answered. An answer is any
message you sent that the carrier accepted, with a non-empty
`IN-REPLY-TO` naming it, a REPLY or a DECISION alike; a failed or
pending send, or one without `IN-REPLY-TO`, answers nothing. It then names the next job's branch: your open
PR's when still addable, else a new one off a freshly fetched default
branch (`--needs-merged` when the job needs your open PR merged first).
Write what you learnt into your memory before you switch.

When the active job is done, delivered, paused, blocked or dropped, run `switch` before
anything else. Do not end the session, wait, or ask what to do while a
job is queued: take it. A session ends idle only when nothing is left
to take, on your list or in your role's pool.

```sh
fabric-jobs switch          # the queued job of highest priority, the oldest first (paused ones first at equal priority)
fabric-jobs switch <id>     # a named queued, paused or blocked job
```

`switch` never preempts an active job: finish, pause, block or deliver it
first. A blocked job keeps its place and is taken only by name. A
blocking job reaches you the next time you ask, never in the middle of
another.

**A fleet hold stops the next job, and nothing else** (ADR-037 rule 13).
fabric-coordinator sets it on your login through the control plane;
the session-start jobs line says `FLEET HOLD:` with its reason and
decision, and `fabric-status` has a `hold` row. While it is set, carry
the active job to its artifact as usual: `block`, `pause`, `deliver`,
`done`, `drop` and `add` work, and a `REQUEST` that arrives is queued
and answered as held. `switch` and `next` settle the job you leave and
then stop, naming the hold: they start nothing and print no
`fabric-fresh`, and `start` and `fabric-fresh --job` refuse. A session
whose job is settled then ends idle; "never idle while a job is queued"
yields to the hold. Only `fabric-ctl <login> unhold` lifts it.

**Nothing queued: your role's pool.** With no queued job on your list
(blocked and delivered ones do not count), `next` starts nothing and
exits 1, saying what your role's open pool holds: its first job, that
it is empty too, or that it could not be asked (an unreachable pool is
never reported as an empty one). It claims nothing. Take an offered
job if you can:

```sh
fabric-jobs pool-list                  # your bound role's unclaimed jobs, highest priority first
fabric-jobs pool-claim <pool-id>       # it lands on your list, queued; one claimant per job
fabric-jobs switch
```

When neither your list nor the pool has a job for you, end the session
with `fabric-fresh --note "<what just finished>"`.

A claim is checked against the role your own control agent reports, and
a job another agent claimed is refused. If a claim was recorded but your
list could not take it, the message gives the command to run again.
Pool jobs are added by the owner (`fabric-ctl <holder> pool-add --role
<role> [--priority P] "<title>"`), as the owner adds a job to one
agent's list (`fabric-ctl <login> jobs-add [--priority P] "<title>"`);
you do not add to a pool.

It starts the job and asks whether this session has already worked one.
Every job after a finished one starts in a fresh session (the owner):

- **This session has worked a job:** "fresh session", whatever the
  project, working copy or topic. It prints `fabric-fresh --job <id>`.
  Run it yourself once this session's work is committed and what you
  learnt is in your memory: it is allowed without a prompt, and it is
  never the owner's to run, so never hand it over as a `!` command or
  ask first. The launcher starts a new session in that job's working
  copy, with the job in its opening prompt.
- **This session has worked no job yet** (launched on its own, not by
  `fabric-fresh --job`, whose session already has its job active) **and
  stands in the job's copy** (its working copy or worktree, or under
  one): "continue here". It is already fresh, so take the job in place.
- **It has worked no job, but stands elsewhere** (another checkout, or a
  place `switch` could not read): "fresh session", the reason said.
  Run the `fabric-fresh --job <id>` it prints, as above. Never `cd` into
  the job's copy instead: the job copy guard reads where the session
  stands and refuses every commit from outside it, and a session keeps
  the hooks and instructions it was launched with wherever it moves.

A fresh session costs this conversation's context, and a cold prompt
cache; that is the point. A launch reads the fabric anew (the prompt,
charter, AGENTS.md, CLAUDE.md and hooks that an upgrade updates on disk and a running
session never re-reads), so a continued session works on stale rules, and
an earlier job's history should not shape the next. If
the session-start context says your active job is in another working
copy, you are in the wrong session for it: continue it there, or block
or deliver it first.

## 4. What the owner sees

`fabric-ctl <login> jobs` lists your open jobs, with their state,
project, topic, source and what each is blocked on. The owner may add a
job to your list (`jobs-add`, source `owner`). Treat it like any
instruction from the owner, and keep its state like your own. Other
agents see whether you have a session running, not your list.

## Never

- Edit `jobs.json` by hand. `fabric-jobs` writes it under the agent lock.
- Remove or edit your own `hold.json`. The fence stops a session that
  missed the announcement, not one that goes round it.
- Two active jobs. Block or deliver one first.
- A job for another agent's work. Their list is theirs; ask them.
- A pool job claimed and left unstarted to keep it from others. Claim
  what you will take next.
