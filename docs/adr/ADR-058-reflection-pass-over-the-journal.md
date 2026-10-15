# ADR-058 — A reflection pass turns an agent's own messages into memory candidates

**Date:** 2026-10-14
**Status:** Accepted
**Ratified:** owner, 2026-10-14, in the coordinator's session ("as you recommend", answering the three choices of the proposal)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** a weekly pass in which each agent reads its own GZCoord journal (`episodic.db`, ADR-041) since its last pass and writes the lessons it finds there as its own memory files; the `fabric-reflect` command that prints what the pass reads; the weekly reflection job; the drain report's count of memories written by a pass
**Pillar:** P1

## 1. Context and Problem

An agent's memory holds only what it chose to write while working. The
drain (ADR-013, ADR-050) curates those files into the shared corpus,
and nothing else reaches it (ADR-041 rule 8). Much of what the fleet
learns is said in messages instead: a decision another role explains,
a correction, a request declined with its reason, a measurement sent
as a reply. Each agent's journal keeps every GZCoord message it sent
and received (ADR-041 rules 1-5), private to its login, and nothing
reads it for lessons. On 2026-10-14 a gateway role declined two
requests because its remit gives the gateway's records to the
coordinator: the coordinator learnt who owns those files from the
decline, and nothing turned that into memory but the coordinator's own
choice to write it.

## 2. Decision

Once a week, before the drain, each agent works a reflection job: it
reads its own journal since its last pass through `fabric-reflect`,
drafts the lessons the messages hold, judges each against the rubric,
and writes the ones that pass as its own memory files, citing the
messages they came from. The drain then takes them as it takes any
memory. The journal is the only source; session transcripts are not
read.

## 3. Alternatives Considered

- **A pass at every job switch.** Fresher, but it adds a step to every
  transition (ADR-037 rule 10) for a store that changes slowly; weekly,
  just before the drain, puts the candidates in front of the one
  reader that takes them.
- **Candidates written unjudged, judged by the drain.** Cheaper for the
  agent, but the drain would judge claims without the context of the
  agent that lived them, and the corpus would fill with noise for the
  flag routing (ADR-050 rule 3) to clean up.
- **Session transcripts as well as the journal.** They hold far more,
  but they are large, they quote tool output, and they can quote what
  a secret looked like; the journal holds what one agent told another,
  already private to its login and filtered for credential shapes on
  read.
- **The coordinator reflecting over every journal.** Refused by
  construction: a journal is readable only by its own login (ADR-041
  rule 1), and knowledge is written by whoever learnt it.

## 4. Rationale

The lessons worth keeping from messages are the ones an agent would
have written had it stopped to: the rubric's tests (memory/RUBRIC.md,
six since ADR-050 rule 7) already say what such a lesson is, and the
agent that sent or received the message is the one able to judge it.
The pass only changes when the agent stops to look. The cost is
bounded: a week of messages, a capped read, one job.

## 5. Binding Rules

1. **A reflection job runs weekly, before the drain.** Each agent's
   list gains one reflection job a week, added by the coordinator
   through the control plane before it drains; the agent takes it as
   any job (ADR-037), never in the middle of another.
2. **The pass reads only the agent's own journal.** `fabric-reflect`
   prints the GZCoord messages the login sent and received since its
   last pass, grouped by thread, with credential-shaped values withheld
   as `fabric-history` withholds them (ADR-041 rule 7). It reads no
   other login's journal and no session transcript, and it reads at
   most a bounded number of messages per pass, saying when more are
   left for the next.
3. **The agent judges; only what passes is written.** Each lesson the
   agent drafts is held to the rubric. One that passes is written as
   the agent's own memory file with a `roles_class`, `origin:
   reflection` and the `MESSAGE-ID`s it rests on; one that fails is not
   written. Hygiene applies as to any memory: people by role, never a
   secret.
4. **The pass moves its cursor only when it finishes.** The last
   message read is recorded in the agent's own state when the job is
   done, so an interrupted pass reads the same messages again; a pass
   that writes nothing still finishes and says so. The closed cursor is
   the job's evidence: a pass lands no PR, commit or reply, so
   `fabric-jobs` settles a job with topic `reflection` as done when the
   login's cursor was closed (`fabric-reflect done`) after the job
   started, and refuses it, naming `fabric-reflect done --through`, while
   there is no cursor, an older one or one it cannot read.
5. **Nothing reaches the corpus but through the drain** (ADR-041 rule
   8). The drain report counts the memories each agent's pass wrote
   (`origin: reflection`), beside the others.

## 6. Consequences

- Lessons said in messages reach the corpus with the name of the agent
  that learnt them, through the same judgement as everything else.
- Each agent spends one job a week on it; a quiet week costs a short
  read.
- `fabric-reflect` and its cursor are built (#264); the weekly job and
  the drain report's count are to build (decided, not yet built; until
  the job is on the lists, no pass runs).

## 7. Future Evolution

Reopened if the passes write mostly what the drain then flags or
retires (the drain report shows it), or if the journal starts holding
more than GZCoord messages.

## 8. Decision Status

Accepted; `fabric-reflect` and the cursor are built (#264); the weekly
job and the drain report's count wait on the coordinator.

## References

- ADR-041 (the journal; rules 1, 7, 8), ADR-037 (jobs), ADR-050 (the
  drain, the rubric's test 6), ADR-013 (the drain), memory/RUBRIC.md,
  tools/fabric/history.py.

## Amendments

The body above reads current; each change's full note is in [history/ADR-058-amendments.md](history/ADR-058-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-15 | A pass is closed by its cursor | §5 rule 4: the closed `fabric-reflect` cursor, dated after the job started, is a reflection job's evidence for `done` |
