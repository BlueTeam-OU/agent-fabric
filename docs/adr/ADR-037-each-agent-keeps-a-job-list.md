# ADR-037 — Each agent keeps a job list

**Date:** 2026-09-28
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** runtime/identity.py (`jobs.json`); bin/fabric-jobs; bin/fabric-fresh (`--job`); runtime/openrouter/launch (the fresh relaunch); runtime/claude-code/hooks/session-start.py; bin/fabric-status; runtime/control/ops.mjs (`jobs`, `jobs-add`); communication/gzcoord/scripts/send.mjs (the inactive intake)
**Pillar:** P3

## 1. Context and Problem

Nothing in the fabric models a job. An agent's work lived in its
conversation, in PR bodies and in `threads` memories. What it had
undertaken, what it waited on and what came next could not be read from
outside its session, and was lost when a session ended.

`fabric-fresh` (ADR-022 rule 10) lets an agent end a finished session.
But when to do so was the agent's judgement alone. Its relaunch always
reopened the launcher's own working copy, and only a 300-character note
crossed to the next session.

The owner asked for a restart when the next job is in another
repository, or on a subject that is basically different, and for a to-do
list per agent where it tracks its jobs and their management.

## 2. Decision

**The list.** Each login keeps one list of its jobs in its runtime state,
`agents/<login>/jobs.json`. It is written only through `runtime/identity.py`
and managed with `fabric-jobs`. A job carries:

- a title;
- its project and working copy;
- a topic, a short label the agent sets;
- a state;
- its source;
- the artifacts that deliver it.

**The restart rule.** At a job's end, `fabric-jobs next` decides whether
the next job continues in this session, or needs a fresh one because its
repository or topic differs. The agent confirms it with
`fabric-fresh --job <id>`. The launcher then starts the fresh session in
that job's working copy, with the job in its opening prompt.

**The fleet view.** The owner reads every agent's list, and adds a job to
one, through the control plane.

**Requests between agents.** A GZCoord request becomes a job only when its
receiver adds it. The automatic intake is built but not activated.

## 3. Alternatives Considered

- **Where the list lives:**
  - *A file committed in each project's repository:* every change would be
    a commit in another role's repository.
  - *GitHub issues:* each job would become an outward artifact.
- **Who decides a restart:**
  - *The agent's judgement alone* is what rule 10 already allowed, and
    nothing guided it.
  - *A launcher that restarts on its own* would end a session the agent
    had not closed.
- **The harness's own to-do tool:** it is absent from the pinned build,
  and it dies with the conversation that a fresh restart drops.

## 4. Rationale

Why these choices:

- **Runtime state:** the list is the agent's working state, like its
  binding, not a project's truth. It stays private to the account, and
  the control plane already reads per-account state for the owner.
- **Topic labels:** a label the agent sets keeps the decision about "a
  basically different subject" with the one who knows the work. The
  command compares labels; it never guesses meaning.
- **An inactive intake:** the owner kept the way agents ask each other,
  and the receiver's control of its own list, unchanged. The code path is
  built and tested, so turning it on later is a switch and a record, not
  a build.

## 5. Binding Rules

1. An agent's jobs live in `agents/<login>/jobs.json`, written only by
   `runtime/identity.py` (`read_jobs`, `update_jobs`, under `agent_lock`).
   A list naming another agent, or written on another host, is refused.
2. A job's state is one of `queued`, `active`, `blocked`, `delivered`,
   `done` and `dropped`, and at most one job per login is `active`.
3. A job carries its project, its working copy and, when the agent sets
   one, a topic. `fabric-jobs next` compares them with the job just ended:
   - the same project, working copy and topic continue in this session;
   - any difference is a fresh session, `fabric-fresh --job <id>`, which
     starts in the job's working copy with the job in its opening prompt.
4. Jobs come from the agent itself (`fabric-jobs add`), and from the owner
   (`fabric-ctl <login> jobs-add`, a signed action). A GZCoord request
   becomes a job only when its receiver adds it (`fabric-jobs add
   --request <MESSAGE-ID>` fills it from the message).
5. The automatic request intake is built and inactive: it runs only under
   `AGENT_FABRIC_JOBS_AUTO_INTAKE=1`, which nothing sets. Turning it on is
   an amendment of this record.
6. The owner reads every agent's open jobs with
   `fabric-ctl <login|all> jobs`, an operator's op. Peers see each other's
   presence, not each other's lists.

## 6. Consequences

- **What becomes readable.** What an agent has undertaken, is doing and
  waits on can be read without opening its session, and survives the
  session's end.
- **What `fabric-fresh` gains.** It carries a job to the next session, in
  that job's own working copy, instead of a note.
- **What it costs.** Keeping a list costs the agent a command at each
  change of a job's state.
- **The limit of a topic.** A topic is only as good as the label: two
  jobs without topics are compared by repository alone, and `next` says
  so.

## 7. Future Evolution

- **Turning the request intake on.** An undertaking REPLY would add the
  request as a queued job. The owed-requests view ADR-024 §6 names would
  then follow from request-sourced jobs.
- **Priorities or due dates** would earn a field when a list is observed
  to need them.

## 8. Decision Status

Proposed. It is accepted by the owner at the merge of the pull request
that builds it.

## References

- ADR-003 — per-agent state is written through `runtime/identity.py`.
- ADR-022 — rule 10, `fabric-fresh`; rule 12, the restart rule.
- ADR-024 — cooperating on requests; §6, the owed-requests list not built.
- ADR-029 — the control plane's ops and signed actions.
