# ADR-047 — Plans: steps the coordinator keeps, each linked to a job

**Date:** 2026-10-09
**Status:** Proposed
**Decision Makers:** the owner (the coordinator keeps the plans); drafted by fabric-coordinator
**Scope:** `tools/fabric/plan.py`, `bin/fabric-plan`; the coordinator's plan files in its state; how a step's state is derived; the plan view (ADR-046)
**Pillar:** P1

## 1. Context and Problem

Work reaches agents as jobs (ADR-037), one per agent's list, with no link
between them: a job has a topic, a source and free-text artifacts, and
nothing says that six jobs on five lists are the steps of one change. The
owner wants to see each job as part of a plan, as a board and as a Gantt
(ADR-046). The coordinator already plans in prose (its plan files); the
plan was nowhere a view could read.

## 2. Decision

The coordinator keeps each plan as data: ordered steps, each with an owner
and the steps it waits for, and each linked to the job queued for it. A
step has no state of its own: it is derived from its job.

## 3. Alternatives Considered

- **Each agent tags its jobs with a plan and step.** Rejected by the owner:
  labels drift between agents, and nobody would own the shape of a plan.
- **A plan field on the job.** Not now: the job model and the `jobs`
  operation are frozen until the cutover (ADR-040 §7), and a link held in
  the plan needs no change to any agent's list.
- **Plans as committed files.** Rejected: a plan changes many times a day
  and holds runtime job ids; a ratified plan is exported into a record or
  a pull request instead.

## 4. Rationale

The coordinator is the role that dispatches the steps (its charter), so the
plan lives where the dispatching happens, and linking a step is part of
queuing its job. Deriving a step's state from its job leaves one place that
says what is done.

## 5. Binding Rules

1. A plan is `{id, title, created_at, status, steps}` and a step `{id,
   title, owner, depends_on, job, est_days?, note?}`, `owner` a login and
   `job` `<login>:<job-id>` or empty. Plans are kept in the coordinator's
   state, `agents/<login>/plans/<id>.json`, written only through
   `runtime/identity.py` (ADR-003).
2. `fabric-plan` (`new`, `step add`, `link`, `show`, `export`) runs for the
   role that holds `fabric-coordinator` and refuses any other.
3. A step's state is its job's; a step with no job is `planned`, or
   `waiting` while a step it depends on is not done; a job that cannot be
   read is `unknown`, with the reason.
4. When the coordinator queues a job for a step (ADR-037 rule 11), it links
   the step in the same act.
5. A plan that is decided is exported (`fabric-plan export`) into the
   record or pull request that decides it; the live plan stays in state.

## 6. Consequences

- The plan view (ADR-046) shows each job as a step, across every agent's
  list, with what waits on what.
- Times on a Gantt come from the linked job's log; a step without one is
  drawn as an estimate.

## 7. Future Evolution

- A plan step given at dispatch (`jobs-add`) once the wire allows new
  arguments (ADR-040 §7), instead of a separate link.

## 8. Decision Status

Proposed: the owner approved the plan in the coordinator's session; this
record awaits the owner's acceptance in its pull request.

## References

- ADR-003 (per-agent state), ADR-037 (jobs), ADR-040 §7, ADR-046 (the
  views).
