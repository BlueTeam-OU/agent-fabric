---
name: agent-jobs
description: "Your own job list: what you have undertaken, are doing, wait on and have delivered, kept with fabric-jobs so it outlives this session; its priorities, a job blocked on another agent's request, your role's open pool, and the restart rule that says what to take next and when it needs a fresh session. Load it when you take on a piece of work, when the session-start context shows a jobs line, when a job reaches its artifact, or before deciding what to do next."
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
| It waits on something | `fabric-jobs block <id> "<the smallest dependency>"` |
| It waits on another agent's request being done | `fabric-jobs block <id> --on-request <MESSAGE-ID>` |
| Its artifact exists | `fabric-jobs deliver <id> <pr-or-commit>...` |
| The artifact landed and nothing is owed | `fabric-jobs done <id>` |
| It will not be done | `fabric-jobs drop <id> "<why>"` |

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

When the active job is done, delivered, blocked or dropped, run `next` before
anything else. Do not end the session, wait, or ask what to do while a
job is queued: take it. A session ends idle only when nothing is left
to take, on your list or in your role's pool.

```sh
fabric-jobs next            # the queued job of highest priority, the oldest first
fabric-jobs next <id>       # a named queued or blocked job
```

`next` never preempts an active job: finish, block or deliver it
first. A blocked job keeps its place and is taken only by name. A
blocking job reaches you the next time you ask, never in the middle of
another.

**Nothing queued: your role's pool.** With your own list empty, `next`
offers the first job in your role's open pool and claims nothing. Take
it if you can:

```sh
fabric-jobs pool-list                  # your bound role's unclaimed jobs, highest priority first
fabric-jobs pool-claim <pool-id>       # it lands on your list, queued; one claimant per job
fabric-jobs next
```

A claim is checked against the role your own control agent reports, and
a job another agent claimed is refused. If a claim was recorded but your
list could not take it, the message gives the command to run again.
Pool jobs are added by the owner (`fabric-ctl <holder> pool-add --role
<role> "<title>"`); you do not add to a pool.

It starts the job and compares it with the job that just ended:

- **Same project, same working copy, same topic:** "continue here". Go on
  in this session.
- **Any of the three differs:** "fresh session". It prints
  `fabric-fresh --job <id>`. Run it once this session's work is
  committed and what you learnt is in your memory. The launcher starts a
  new session in that job's working copy, with the job in its opening
  prompt.
- **A job without a topic:** only the repository is compared, and `next`
  says so. If the subject differs anyway, it is a fresh session all the
  same.

A fresh session costs this conversation's context; that is the point. A
different repository or subject should not read this one's history. If
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
- Two active jobs. Block or deliver one first.
- A job for another agent's work. Their list is theirs; ask them.
- A pool job claimed and left unstarted to keep it from others. Claim
  what you will take next.
