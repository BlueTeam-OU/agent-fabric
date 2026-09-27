# ADR-016 — Skills carry rules, not history

**Date:** 2026-09-19
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** every `SKILL.md` the fabric ships — policies/subagent-dispatch/SKILL.md, communication/gzcoord/skills/, identities/roles/*/skills/; tools/fabric/lint.py (`project_name_findings`)
**Pillar:** P2

## 1. Context and Problem

A skill is procedure for the session that loads it — on any account, in
any project, for as long as the rule holds. On 2026-09-19 the
coordinator added a step to the receive skill that cited the incident it
came from: a date, two pull-request numbers of one managed project. The
corpus lint refused the project's name in a generic file; the owner
refused the citation and the date, and pointed at the skill-creator's
own guidance — general, imperative, the *why* explained without the
specific example it was learnt from.

The sweep that followed found the pattern in five of the six skills the
fabric shipped, 22 lines; the dispatch skill read as a dated history.
A date, a PR number, an incident's project or login narrows a rule to the
one occasion that prompted it and reads as history to a session that
needs an instruction.

What the sweep removed, and where its evidence now is (the commit that
made the sweep, 43ef828, carries the passage each came from):

- **Subagent dispatch:** the forty-agent bill of a fold dispatched with
  `model` unset from a premium session (2026-08-05); the alias guard that
  checks rather than infers (2026-09-13); a reviewer on `opus` that ran on
  GLM on the broker path (2026-09-13); broker pricing checked against the
  provider's docs and catalogue, the launcher and registry shipped
  (2026-09-12); the read-only harness types' exemption after every
  Explore dispatch of a planning session was denied (2026-09-16); the
  locale worker's one tool read back (2026-09-17); `worktree.baseRef`
  defaulting to `fresh` (found 2026-08-04, reproduced 2026-08-07); `head`
  as the committed HEAD (2026-08-07, re-verified 2026-09-11); the
  embedded-repository gitlink and parallel worktree creation (2026-08-07);
  the review status tool moved into the fabric (`runtime/github/`,
  2026-09-19).
- **Receive:** the watch from the first turn;
  reply only to add something useful; the
  notification cut inside a REQUEST or VERIFIED (four deliveries,
  2026-09-16); an assignment to a role claimed by the first REPLY (two
  holders of one role, 2026-09-19).
- **Send:** an assignment goes to one login.
- **Client capture:** written from one login's Linux desktop build
  (2026-09-16).
- **pg-probe:** the "ship it commented out" pattern, folded into a
  project's baseline migration by its 2026-07-20 re-baseline.

## 2. Decision

A skill states the rule and the reason it holds, in general, imperative
terms, and nothing of the occasion that taught it. What happened, when
and to whom — the evidence — goes in the commit that changes the skill,
in a live check, or in the decision record the skill applies; the skill
points at a record or a live check only where a reader needs the
pointer. Before writing or changing a `SKILL.md`, the author loads the
skill-creator skill and follows it.

A pointer to the home of a rule the skill applies is not an incident and
may stay.

## 3. Alternatives Considered

- **Keep the incident beside the rule, as provenance.** Rejected: it
  narrows the rule to one occasion, costs every session that loads the
  skill, and dates it.
- **Drop the evidence.** Rejected: the provenance must be one hop away;
  it moved to the commit and, for this sweep, to this record.
- **Evidence in a note under `docs/`** (the rule as first written).
  Superseded by ADR-001 §5 rule 3: a decision is never a free-standing
  note; evidence is a live check, a record, or a commit.

## 4. Rationale

A skill is loaded by description match, in any project, by any holder;
its text is paid for on every load. What makes it useful is that it
tells the session what to do and why; what makes a decision trustworthy
is its evidence, which belongs where evidence is kept and reviewed
(ADR-000, P2: a working method becomes a practice every role reads).

## 5. Binding Rules

1. No `SKILL.md` the fabric ships carries a date, a pull-request or issue
   number, a managed project's name, or a login as the occasion of a rule.
2. Each rule in a skill carries its reason, stated generally.
3. The evidence for a rule lives in the commit that wrote it, a live
   check (`docs/live-checks/`), or the decision record it applies; a skill
   points there only where the pointer is needed.
4. A pointer to the home of a rule the skill applies (a record's number
   and section) is allowed; outside the repository that owns the record,
   it names that repository (ADR-001 §5 rule 6).
5. Whoever writes or changes a `SKILL.md` loads the skill-creator skill
   first and follows it.

## 6. Consequences

- Lint enforces part of rule 1 only: `project_name_findings` refuses a
  managed project's id in `identities/roles/` (role skills included) and
  `communication/gzcoord/skills/`, among other generic directories. It
  does not scan `policies/subagent-dispatch/SKILL.md`, and nothing checks
  dates, PR numbers or logins in a skill: rules 1, 2 and 5 are held by
  the author and by review. On 2026-09-27 no shipped skill carries a date
  or a PR number.
- A skill's history is read with `git log` on the skill.

## 7. Future Evolution

- **Open — pg-probe's pointers.** `identities/roles/db-admin/skills/pg-probe/SKILL.md`
  cites gzapp's ADR-018 and gzapp's ADR-022 §5 rule 9 by bare number:
  one managed project's records, the rules the skill applies. Two things are
  unsettled: whether the project-bound half of that skill belongs in
  that project's `.agent-fabric/` remit for `db-admin` rather than in a
  role skill under `identities/roles/`; and, now that agent-fabric
  numbers records of its own, that a bare number there reads as this
  repository's to a reader here (rule 4 asks for the repository's name).
- A lint for dates and numbers in skills is a candidate if the pattern
  returns.

## 8. Decision Status

Accepted: the owner's rule of 2026-09-19, applied to every skill by the
sweep of that day (commit 43ef828). The note that recorded the sweep is
now a stub pointing here.

## References

- Commit 43ef828 (the sweep, and each removed passage in its diff).
- `tools/fabric/lint.py` (`project_name_findings`, `GENERIC_DIRS`).
- `.agent-fabric/memory/fabric-coordinator/workflow/skills-no-prs-no-dates.md`
  (the coordinator's own lesson).
- ADR-001 (§5 rules 3 and 6), ADR-000 (P2).
