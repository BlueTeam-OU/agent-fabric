# ADR-067 — One owning module per cross-cutting mechanism

**Date:** 2026-11-08
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the fabric's cross-cutting mechanisms (per-agent state, process lifetime, agent context, remote evidence completeness, the job lifecycle, message transport) and the catalogue that names each one's owning module, its checker and its declared exceptions: `policies/mechanisms.json`, read by `tools/fabric/lint_rules/mechanisms.py`. Not what each mechanism decides, which stays in its own record (ADR-003, ADR-037, ADR-045, ADR-064)
**Pillar:** P1

## 1. Context and Problem

An external architecture review of agent-fabric, which the owner
commissioned and read on 2026-11-08, found the decision records coherent
and the mechanisms that carry them duplicated. The same invariant is
implemented in several modules; one keeps the rule and a sibling breaks
it. Four of the review's bug findings (F02, F03, F06, F08) are that
shape. Read against `origin/main` at 27af8227 the same day:

- **Process lifetime.** Fourteen modules outside the tests start or kill
  process groups themselves (`killpg`, `start_new_session`, `setsid`),
  although `tools/fabric/provisioning/bounded.py` exists. #477 fixed two
  sites and left the siblings to a later job.
- **Remote evidence completeness.** The 3,000-file cap moved into
  `tools/fabric/github/common.py` with F08; the 250-commit cap is still
  five constants in five modules (`arm.py`, `pr_counts.py`,
  `post_review.py`, `review_checkpoint.py`, `results.py`), each
  deciding for itself whether a capped list is complete.
- **Agent context.** `identity.resolve_context` is canonical, yet
  `query.py`, `memory_mcp/server.py` and `launch.py` open
  `binding.json` themselves.
- **The job lifecycle.** A job's state is changed by `fabric-jobs`'
  verbs, `switch`, the hourly sweep, the inbox intake, `jobs-add` and
  the role pool, and no rule said which changes exist (ADR-037 rule 14,
  A 2026-11-08).
- **Per-agent state.** The review counted fifteen writers outside
  `runtime/identity.py`. That count is out of date: j576 (#497) and
  j577 (#506) closed all but one, and `tools/fabric/state_writes.py` with
  `policies/state-writers.json` already enforces ADR-003 rule 1 in
  lint, the pre-commit hook and the suite. It is the pattern the other
  mechanisms lack.

Each record says what its mechanism decides. None says that only one
module may implement it, so each new feature is free to write its own
copy, and a review catches the copy only when it already disagrees.

## 2. Decision

A cross-cutting mechanism has one owning module. Every other module uses
it and never reimplements it. Each mechanism has a checker that finds a
reimplementation in the tree, and an exceptions file in which every
exception carries its reason, on the model of `state_writes.py`.

`policies/mechanisms.json` is the catalogue: for each mechanism, the
record it comes from, its owning module, its checker and exceptions
file, and whether it is enforced yet or which job will enforce it. Lint
reads the catalogue and refuses one that names a missing module or
claims enforcement it does not have.

## 3. Alternatives Considered

- **A rule in prose only.** The duplicates arose under records that were
  already clear; a review that reads every new module for every
  mechanism is the cost this replaces.
- **One shared framework (a `StateStore`, a service layer) for all
  mechanisms.** `runtime/identity.py` already has `atomic_write`,
  `append_line` and `agent_lock`; the missing piece is the fence, not
  another abstraction.
- **One checker for every mechanism.** Each mechanism's reimplementation
  looks different in the syntax tree (a `killpg`, a constant 250, a
  path ending `binding.json`); one predicate per mechanism keeps each
  readable and each exception list short.
- **Fix the instances and add nothing.** That is what #477 and F08 did;
  the siblings stayed.

## 4. Rationale

`state_writes.py` showed the shape works: since j535 a new state writer
outside `identity.py` is refused at commit, in CI and in the suite, and
the gaps it named were closed one by one rather than rediscovered. An
exception list with a reason per entry keeps a legitimate exception
visible and makes a stale one a lint finding. The catalogue gives the
owner and a reviewer one place to read which mechanisms are fenced, and
lets lint check that the claim is true.

## 5. Binding Rules

1. A mechanism in `policies/mechanisms.json` is implemented only in its
   owning module. Another module uses that module's interface; a
   reimplementation is a finding unless the mechanism's exceptions file
   names the module with the reason that admits it.
2. Each catalogue entry names the record the mechanism comes from and
   its `status`:
   - `enforced`: its owning module, checker and exceptions file are
     named, and the checker is loaded by a lint rule that lint runs
     (so CI runs it), by the pre-commit hook and by a case under
     `tests/`, as a guard is;
   - `pending`: its owning module is named and its checker is being
     built; the entry names the job building it as `<login>/j<n>`, and
     the checker's paths enter with enforcement;
   - `planned`: decided here, its owner not yet built; the entry says
     what it waits on and names the owner once it exists.
3. Lint reads the catalogue on every run. A finding is: a catalogue
   that is not JSON; an entry missing a field rule 2 asks for of its
   status; any path an entry names that is not a tracked file; an
   `enforced` entry whose checker is not loaded where rule 2 says, a
   load being an import or lint's `_load` call, never a mention. An
   absent catalogue is no finding: `policies/*.json` is instance data
   (ADR-045 rule 2).
4. A new cross-cutting mechanism enters the catalogue in the same pull
   request as its owning module. A pull request that adds a second
   implementation of a catalogued mechanism moves it into the owner or
   declares it, with its reason, in the exceptions file.
5. The catalogue and every exceptions file are fabric-coordinator's
   (`policies/`, ADR-018). A contributor that builds a checker
   supplies its exceptions file on a `for/` branch, and
   fabric-coordinator wires the checker into lint (and so CI), the
   pre-commit hook and a `tests/` case, as rule 2 asks, and marks the
   entry `enforced`.

## 6. Consequences

- **What gets easier.** A reviewer asks one question of a new module
  that starts a process, reads a binding or counts a pull request's
  commits: does it go through the owner? The checker answers it before
  the review.
- **What gets harder.** A feature that needs something the owning module
  lacks extends the owner instead of writing a local copy, which may
  mean a supply across lanes.
- **What it costs.** One checker and one exceptions file per mechanism,
  and a lint rule over the catalogue.

## 7. Future Evolution

- Each `pending` entry becomes `enforced` as its job lands (Wave 1 of
  j674: process lifetime, remote evidence, agent context). The job
  lifecycle and transport are `planned` until their owners exist (a
  `work/` module over ADR-037 rule 14; a transport interface under
  ADR-064, with the relay still primary).
- A mechanism the catalogue lacks is added when a duplicate of it is
  found, not before.

## 8. Decision Status

Proposed. Rules 2 and 3 are built with this record (the catalogue,
its lint rule and `tests/test_mechanisms.py`). Per-agent state, agent
context and remote evidence are `enforced`: the second by
python-dev-01's j212 (`tools/fabric/context_reads.py`,
`policies/context-reads.json`), the third by python-dev-03's j119
(`tools/fabric/github/evidence.py`, `tools/fabric/evidence_caps.py`,
`policies/evidence-caps.json`). Process lifetime is `pending` on
python-dev-02's Wave 1 job; the job lifecycle and transport are
`planned`.

## References

- ADR-003 — per-agent state written through `runtime/identity.py`; rule 1 and `state_writes.py`, the pattern.
- ADR-018 — `policies/` is fabric-coordinator's.
- ADR-037 — the job list; rule 14, the transition table the job lifecycle's owner will implement.
- ADR-045 — roots; where instance data is read from.
- ADR-064 — the relay and InterWeave dual run; the transport's owner sits behind it.
- `policies/mechanisms.json`, `tools/fabric/lint_rules/mechanisms.py`.
