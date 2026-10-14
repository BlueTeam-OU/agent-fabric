# ADR-055 — Model availability is rediscovered by each run; the control plane reports it to people; a review diverts only when its engine is the only one required

**Date:** 2026-10-13
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** `routing/policies/availability.json` and its schema; how an engine run learns a model is unavailable and what it does (`tools/fabric/review_codex.py`, the review engines to come); each provider's strategy, its review models in order (`routing/policies/availability.json`, its first model the one `routing/capabilities.json` routes, all inside `routing/policies/review-grade.json`); the control plane's report of what runs observed, for people (`fabric-ctl`, the Board); the review divert
**Pillar:** P1

## 1. Context and Problem

Every pull request now needs a Claude and a Codex review (ADR-053 rule
6, `policies/arming.json`). On 2026-10-13 a Codex review from
python-dev-01's login ran once and then failed twice within minutes:
the ChatGPT backend answered "Selected model is at capacity" — the
provider's model was full for everyone, not our allowance spent. With
the review required, such a spell stops every merge in the fleet.

Two kinds of unavailability look alike to a run and are not alike:

- **At capacity** — the provider's, transient, minutes; nothing of ours
  changes it.
- **Over allowance** — ours: a subscription's five-hour or weekly
  window spent, until a known reset (ADR-031's windows; ADR-052 reads
  them through the gateway's usage operation for Claude accounts).

Today each run rediscovers either one alone. The engine is being taught
to retry a capacity failure (10 s, 20 s, 60 s, then report which kind it
was), but the next run on another login learns nothing from it; the
account switch (ADR-052) knows the Claude windows and nothing about
OpenAI's; routing resolves a class to one model and never asks whether
it can be served.

## 2. Decision

Each run rediscovers availability for itself, locally: it tries its
model, retries a capacity failure (10 s, 20 s, 60 s), and decides from
what it saw — never from a record another run left. When its model is
unavailable after the retries and its engine is the only one the
pull request's policy requires, a review diverts to the next model of
its provider's ordered list; otherwise it reports and the pull request
waits. The
control plane keeps what runs observed — which model, which kind, when
— only to tell people: `fabric-ctl` and the Board show it, and the owner
is told of a long or total outage. Nothing in routing or in a run reads
that report to choose a model.

## 3. Alternatives Considered

**A central availability record that routing consults.** One run's
discovery would spare the next 24 their retries, but a stale mark takes
a model out of service for runs that could have used it, the record
becomes a single writer every review depends on, and a capacity spell is
minutes long: the cost it saves is seconds of retry. Rejected by the
owner: availability is rediscovered locally.

**No report at all.** Each run copes alone and nobody learns that a
model has been full for an hour; the owner finds out from stalled merges.

**Always divert, never wait.** Reviewing on a different model than
policy names makes the second engine's point — a different reviewer —
depend on the weather; diverting only when the engine is the pull
request's only required one keeps a review happening without quietly
replacing the contrarian one.

**Fold it into ADR-052.** That record moves a Claude session between
accounts on usage windows; this one decides what a one-shot run does
when its model cannot serve it. They share readings, not decisions.

## 4. Rationale

Availability changes faster than any record of it: a capacity spell
lasts minutes and differs from one moment to the next, so the only
trustworthy answer is the one a run gets by asking. Local rediscovery
keeps every run independent of a shared writer. People, though, need the
pattern a single run cannot see — the same model full all afternoon, or
an allowance spent — and the control plane already gathers what the
fleet reports (ADR-029), so it carries that view.

## 5. Binding Rules

1. A run learns availability by trying: it never skips or picks a model
   because of what another run observed.
2. An engine retries a capacity failure after 10 s, 20 s and 60 s, then
   reports "the chosen model is unavailable" with its kind: at capacity
   (the provider's) or over the allowance (ours, with the reset time
   when the provider gives one). An allowance failure is not retried
   past what can help; any other failure is not retried.
3. A review diverts to the next model of its provider's ordered list
   for the review capability (`routing/policies/availability.json`,
   rule 7, inside the review-grade set) when its own model is unavailable after the retries and it is
   the only engine the policy requires for that pull request. When the
   policy requires another engine as well, there is no divert: the
   review reports and the pull request waits for the engine to return.
   A divert never lands on a model of a provider whose engine the
   policy also names — the Codex review never falls back to a Claude
   model — so a second review stays a different reviewer. The posted
   review names the model that ran and that it was a divert; it counts
   for the engine that was required.
4. Every unavailability a run meets is reported to the control plane —
   model, seat, kind, time, the provider's words — through the
   account's control agent. The report is for people: `fabric-ctl
   <login|all> availability` and the Board show it.
5. Nothing reads the report to choose a model: not routing, not an
   engine, not the launcher.
6. A model reported unavailable for longer than an hour, or every model
   of the review capability reported unavailable at once, is said to the
   owner, once per episode.
7. Each provider's strategy is data, in one syntax for every provider:
   `routing/policies/availability.json` gives its retry waits, its seats
   in order, what an allowance failure does (`next-seat` or `report`)
   and, per capability, the ordered models a run tries, the routed one
   first and, for review, only review-grade ones; lint judges it against
   its schema, routing and the account-switch pool. A provider with one
   seat and one model is less fault-tolerant by construction, and the
   file says so rather than the code: OpenAI today, against Anthropic's
   two seats and three review models.
8. A second review engine is additional, never blocking (A 2026-10-13):
   `policies/arming.json` requires the claude review (`reviews`,
   `boundary_reviews`) and lists codex under `additional_reviews`, the
   marker tool having landed (#245); codex is optional, never blocking.
   The arm accepts, for an additional engine, its review of the head (whose
   open P1 or P2 still blocks) or its unavailable marker for that exact
   head, posted by `fabric-review --engine codex` when the engine cannot
   run (over the allowance, or at capacity after rule 2's waits) as a
   review object from an account whose reviews count; with neither, the
   engine is absent: the arm proceeds on the required reviews and says
   "codex: absent" in its summary and posted basis, and the gate reads it
   the same way. Never paid API spend in its place: the engine rides the
   subscription only.

## 6. Consequences

- Each run pays its own retries: on a capacity spell, 90 s of waits and
  up to three more full attempts, each within the engine's time budget
  (capacity is known only when a turn ends); no run is ever blocked by a
  stale mark.
- People see a capacity or allowance pattern across the fleet without
  running a review, and the owner hears of a long outage.
- Routing gains an order for the review capability; a model added to
  the review-grade set must also be placed in it.
- A diverted review is a different reviewer by construction; it is
  visible on the review and in the report, never silent.

## 7. Future Evolution

A review loop of the fabric's own — read-only tools driving any
review-grade model through the gateway's Responses listener, on the
same subscription — would make the reviewer provider-neutral and the
divert of rule 3 a model choice rather than an engine swap; Codex stays
the engine while it serves. If the report shows retries costing real time across the fleet, a
shared hint could be revisited — as advice a run may read, never a rule
it must follow. Session-level failover, moving a running session to
another model, is outside this record. The one-hour owner notice is a
first number.

## 8. Decision Status

Proposed. The owner set its shape in the coordinator's session:
retries of 10 s, 20 s and 60 s; a report naming capacity or allowance;
availability rediscovered locally, tracked centrally only to let people
know; a divert only when the engine is the pull request's only required
reviewer, so under the fleet's two-engine policy a pull request waits
out an outage; and a divert never onto the other engine's provider.
The engine's retries and report (rule 2) are built (#235); the report
to the control plane and the divert follow acceptance.

## References

- ADR-002 (fixed at launch), ADR-005 (routing), ADR-029 (the control
  plane), ADR-031 (accounts and windows), ADR-052 (the account switch),
  ADR-053 (the second review engine, rule 6 as amended 2026-10-13).
- `routing/capabilities.json`, `routing/policies/review-grade.json`,
  `tools/fabric/review_codex.py`, `policies/arming.json`.

## Amendments

The body above reads current; each change's full note is in [history/ADR-055-amendments.md](history/ADR-055-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-13 | Codex is an additional review: unavailable, the claude review alone arms | §5 rule 8: arming.json reviews claude, additional_reviews codex; review or unavailable marker per head; no API spend |
| 2026-10-14 | An absent additional review does not stop an arm | §5 rule 8: neither review nor marker on the head is "absent"; the arm proceeds and says so; the gate reads the same |
