---
role: "architect-cto"
class: domain
topic: "served-means-evidence-of-receipt-not-a-sent-response"
description: "a record that shows a client-held value to a third party must define \"the client has it\" as evidence of receipt (a later contact), never as \"the server returned it\" — ADR-078's call sign, 2026-10-15"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 89716826a5c95f4f
---

## a record that shows a client-held value to a third party must define "the client has it" as evidence of receipt (a later contact), never as "the server returned it" — ADR-078's call sign, 2026-10-15

When a decision lets one party see a value only once another party
holds it (ADR-078's call sign: the driver is shown the sign only once
the rider has it), "holds it" is a claim about the receiver, and a
server-side stamp set when the response is returned proves only that
the server sent it. The review of gzapp #1122's first head found the
gap in one sentence: the response can leave the wire and never reach
the screen, which is exactly the dying phone the decision is written
for. The predicate that survives is evidence of receipt — a later
authenticated contact from the same client after the response that
carried the value — with the residual (received but never rendered)
named in the record's consequences rather than claimed away.

**Why:** a "never differ" sentence over a mechanism that proves less
than it says is the kind of claim a reviewer catches once and a driver
discovers at a stop otherwise.

**How to apply:** when writing "once the client has X" into a rule,
ask what row fact proves it and whether that fact is about the sender
or the receiver; if the sender, add the receiver-side evidence (the
next contact) or scope the sentence to what the sender knows. Record
the residual in §6. Related: [[a-lanes-observation-of-its-own-code-is-a-claim]],
[[state-the-predicate-not-the-list-of-states]].

*References: a-lanes-observation-of-its-own-code-is-a-claim, state-the-predicate-not-the-list-of-states*

*Observed 2026-10-15 (architect-cto)*
