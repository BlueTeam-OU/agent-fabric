# ADR-026 — Progress is measured as supervision per verified result

**Date:** 2026-09-27
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** how the fabric would measure its progress under pillar P3: the definitions of a verified result and of a supervision event, the artifacts they are read from, and how the number may and may not be used; no tool, file or practice is changed by this record
**Pillar:** P3

## 1. Context and Problem

ADR-000 states P3's direction: "Progress is measured by how much less
supervision a correct, verified and maintainable result needs, not by how
many messages the agents exchange." Nothing measures it today. The
counts that are easy to take — messages sent, PRs opened, commits, agents
running — reward activity, and the survey behind ADR-024 found the
fleet's costliest failures (work done twice, states announced before they
were true) in exactly the places where activity was high.

Supervision is also scattered (ADR-000 §5, P3): the arming band's
"ask the owner", the ratification of records, the authority guard, the
owner's word carried in a message. Without one definition, "the owner was
needed less" cannot be told from "the owner was asked less and caught
less".

This record proposes the measure. It builds nothing and claims nothing as
existing.

## 2. Decision

Proposed: the fabric's progress under P3 is read as **supervision per
verified result** — the number of supervision events attributable to a
period's verified results, divided by the number of those results —
tracked as a trend over time, per repository and in total, and never set
as a target.

- A **verified result** is a merged pull request whose head carried a
  review (ADR-020) and green checks when it merged (ADR-019), and that
  was not reverted, and received no fix naming it, within a fixed window
  after the merge (fourteen days proposed). The window is what makes
  "maintainable" observable: a result that needed a fix-forward was not
  yet correct.
- A **supervision event** is an intervention by the owner that the
  result needed and that reached an artifact:
  1. an `OWNER-WORD` section in a relay `DECISION` (ADR-024 §5 rule 9);
  2. an arming the owner had to make or approve — a PR under the band's
     floor, or one ratifying a new direction (ADR-019 §5 rule 4, ADR-001
     §5 rule 2);
  3. a correction by the owner recorded in a commit or PR — the fabric's
     habit of naming the owner and a date in a commit subject or a
     record's Decision Makers;
  4. a collision the owner had to decide in a drain (ADR-014 §5 rule 3).
  What is not supervision: the owner setting direction (a new pillar, a
  new policy stated unprompted), and every check a machine makes (the
  gate, the review class, the guards). The first is the owner's role, not
  a cost of the result; the second is verification, which the measure
  wants more of, not less.

## 3. Alternatives Considered

- **Messages exchanged, or PRs merged, per period.** Rejected by P3's
  own wording: activity is not progress, and both reward the rework the
  fleet most needs to lose.
- **Owner time.** The truest input, and not observable from artifacts:
  every session and the owner act through one GitHub account, and the
  owner's reading time leaves no trace. The events above are the part of
  it that does.
- **A per-agent score.** Rejected: a result often spans lanes (a caller
  and its suppliers, ADR-019), and a per-agent number invites optimising
  one's own row at another's expense.
- **A target** ("under 0.2 events per result"). Rejected: the memory
  rubric's lesson (`memory/RUBRIC.md`, "Telemetry, not quotas") — a
  quota manufactures what it counts. Told to need
  less supervision, a fleet can simply ask less; the trend is read beside
  the verification rate for that reason.

## 4. Rationale

The measure puts the two things P3 promises on one line: autonomy (less
supervision) and verifiable commitments (only verified results count). A
fall in the numerator with a steady verified-result rate is progress; a
fall in both is a fleet that stopped asking and stopped landing. Reading
it only from artifacts keeps it auditable and keeps it out of the
agents' private context.

## 5. Binding Rules

Proposed — none binds until the owner accepts this record.

1. The measure is supervision events per verified result, per period (a
   week proposed), per repository and in total, published with its
   numerator, its denominator and the verified-result rate (verified
   results over merged PRs) beside it.
2. A verified result and a supervision event are as defined in §2; a
   change to either definition is an amendment of this record, and the
   series is recomputed from the start under the new definition rather
   than spliced.
3. Every input is read from artifacts: the PR record (merge, head sha,
   checks, the review marker, reverts and fixes naming the PR), commit
   subjects and trailers, decision records, drain reports
   (`collision_decisions`), and in relay messages only the type, the
   metadata and the presence of an `OWNER-WORD` section — never a
   message body otherwise, never a session transcript, never an agent's
   memory.
4. The number is never a target for any agent, never compared between
   agents, and never a reason to withhold a question from the owner; a
   session that needs the owner's word asks for it.

## 6. Consequences

- If accepted, a counter is owed: nothing reads these artifacts today.
  `runtime/github/commit-class.sh` already separates review fixes from
  work; `pr-review-status.sh` already says whether a head was reviewed;
  drain reports already record `collision_decisions`. The relay's
  `OWNER-WORD` count needs a reader over message metadata and section
  markers, which does not exist.
- Attribution is the hard part: every merge and comment on GitHub comes
  from one account, so an owner's arming can be told from a session's
  only by what the artifacts say (an arming basis comment, the owner's
  word cited), not by who clicked.
- P7's direction — cost per verified result, beside this one — shares the
  denominator.

## 7. Future Evolution

Once a counter exists and a few weeks of series are in, the owner decides
whether the definitions hold. P3's other direction, the mandate stated as
a whole, is what would move events of kind 2 out of the numerator: a
rule that says what the owner need not see turns an ask into a check.

## 8. Decision Status

Proposed, 2026-09-27. It waits on the owner's acceptance of the measure
and its two definitions, individually (ADR-001 §5 rule 2: arming the
pull request that carries it does not ratify a new direction unless the
description says so and the owner arms it on that basis). Until then it
binds nothing and nothing is built for it.

## References

- ADR-000 §5, P3 (Today, Direction) and P7 (Direction).
- ADR-001 (§5 rule 2), ADR-014 (contested claims), ADR-019 (the band and the gate), ADR-020
  (the review), ADR-024 (carrying the owner's word).
- `runtime/github/commit-class.sh`, `runtime/github/pr-review-status.sh`,
  `runtime/github/pr-gate.sh`; `memory/RUBRIC.md` ("Telemetry, not
  quotas").
