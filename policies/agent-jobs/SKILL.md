---
name: agent-jobs
description: "Your own job list: what you have undertaken, are doing, wait on and have delivered, kept with fabric-jobs so it outlives this session, and the restart rule that says when the next job needs a fresh session. Load it when you take on a piece of work, when the session-start context shows a jobs line, when a job reaches its artifact, or before deciding what to do next."
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

## 2. Keep its state true

| When | Run |
|---|---|
| You start on it | `fabric-jobs start <id>` (one job is active at a time) |
| It waits on something | `fabric-jobs block <id> "<the smallest dependency>"` |
| Its artifact exists | `fabric-jobs deliver <id> <pr-or-commit>...` |
| The artifact landed and nothing is owed | `fabric-jobs done <id>` |
| It will not be done | `fabric-jobs drop <id> "<why>"` |

`fabric-jobs list` shows the open jobs. `fabric-jobs show <id>` shows one
in full.

## 3. What comes next: the restart rule

When the active job is delivered, blocked or done, run `next` before
anything else. Do not end the session, wait, or ask what to do while a
job is queued: take it. A session ends idle only when nothing is left
to take.

```sh
fabric-jobs next            # the oldest queued job
fabric-jobs next <id>       # a named queued or blocked job
```

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
