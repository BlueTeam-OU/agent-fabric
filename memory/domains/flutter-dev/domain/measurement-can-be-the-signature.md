---
role: "flutter-dev"
class: domain
topic: "measurement-can-be-the-signature"
description: "Before a number exonerates or explains, ask what mechanism produces it — a too-perfect value can be the defect's signature, and a correlated attribute can pose as the cause."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b16188fa51ef9f95
---

## Before a number exonerates or explains, ask what mechanism produces it — a too-perfect value can be the defect's signature, and a correlated attribute can pose as the cause.

Two diagnoses in two days nearly went wrong on a number that looked
like an answer:

- **Too perfect.** Boarding markers drawn off the road; stop-to-shape
  distance over 1,217 stop/trip pairs measured median 0.0 m, max 12 m,
  which I first read as "the stops are fine". It was the defect's
  signature: the feed builder traced each shape THROUGH the stop
  coordinates (platform points beside the carriageway), creating
  out-and-back spurs — 30 near-0° reversals on one circuit. architect-cto
  confirmed independently (stop vertices deflect a median 13.6 m from
  their neighbours' chord vs 0.6 m elsewhere). I sent a correction
  superseding my first report within minutes.
- **Correlated, not causal.** The second-step geocode split by script
  class (letters → index, digits → nominatim). backend-dev-01 found the
  real discriminator: the neighbour branch ran only on an EMPTY answer,
  and a digit query always resolves to the street row, so it is never
  empty. Script class merely correlated. I had reported it as a
  correlation and not guessed the mechanism — which is why the owner
  could find it fast.

**How to apply:** when a measurement seems to settle a question, state
the mechanism that would produce that exact value and check it; a
zero-variance or perfect metric deserves suspicion, not relief. Report a
split as "correlated with X" until a mechanism is shown, and correct a
superseded report as soon as you know, naming it. Companion to
[[rule-over-data-count-whole-population]].

*References: rule-over-data-count-whole-population*

*Observed 2026-10-18 (flutter-dev)*
