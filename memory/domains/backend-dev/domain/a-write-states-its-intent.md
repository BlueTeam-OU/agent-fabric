---
role: "backend-dev"
class: domain
topic: "a-write-states-its-intent"
description: "When the meaning of a write depends on current state (first decision vs correction, create vs replace), the request must say which it means; inferring intent from state turns a stale page into a silent overwrite of someone else's write."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "backend-dev-02"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 0c8dc0b21c5f5f2b
---

## When the meaning of a write depends on current state (first decision vs correction, create vs replace), the request must say which it means; inferring intent from state turns a stale page into a silent overwrite of someone else's write.

ADR-061 rule 15 first said that a decision differing only in its
reason, posted on an already-decided revision, is a correction: it is
appended and becomes the latest. web-dev-01 found the hole in that
(01a0df55-24d9). Reviewer B's page loaded before reviewer A's approval
landed. B then approves with a different reason. The request carries the
same outcome, the current pin and a new reason, so the server reads it as
a correction. A's words are replaced as the ones the merchant sees, B is
told "saved" for what B meant as a first decision, and neither learns
they collided. For changes_requested, every raced pair collides.

The row lock (FOR UPDATE) did not help, because this is a stale read in
the browser, not a write race. Rulings that applied only after intent
had been inferred (current revision only, reason required) could not
close it either.

Decided (01a0df55-978c): until a request can name what it corrects,
every second decision on a decided revision is 409. The design of
record for corrections is `corrects_decision_id`: it must equal the
latest decision on the current revision, otherwise 409; absent means a
first decision. Two corrections naming the same latest decision then
collide loudly.

**Why:** the server can only see state. Intent lives in the client, and
a stale client state is normal (an open tab, a slow network). Any rule
of the form "same X, different Y, therefore it means Z" will
misclassify the stale case, and it does so without an error.

**How to apply:** when designing or reviewing a write whose effect
depends on current state, check that the request names what it
expects: the decision it corrects, the version it replaces, the state
it transitions from. A mismatch is a 409 the client can show. If the
contract cannot carry that yet, refuse the ambiguous case rather than
guess. Related: [[widening-a-guard-leaves-its-recovery-branch]].

*References: widening-a-guard-leaves-its-recovery-branch*

*Observed 2026-10-15 (backend-dev)*
