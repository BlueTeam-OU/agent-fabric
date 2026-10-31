---
role: "web-dev"
class: workflow
topic: "repeat-a-transition-to-test-the-server-guard"
description: "When a screen sends a state transition (approve, publish, deprecate) or words a dialog about one: check the server refuses it from the wrong state before trusting the UI's hidden button"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c7b3dbd6a37b4a58
---

## When a screen sends a state transition (approve, publish, deprecate) or words a dialog about one: check the server refuses it from the wrong state before trusting the UI's hidden button

A screen that hides or disables an action once its subject has moved on
is not a guard: a page loaded before another reviewer acted still sends
it. Twice a backend accepted a transition from the wrong state, and both
times the web side found it: a review approval repeated with the same
body answered 201 again and appended a second evidence row (found from a
stale page); a publish endpoint had no status predicate, so a deprecated
version could be re-activated (found while wording a deprecate dialog,
which needed to know whether deprecation is final).

**Why:** the client's view of a lifecycle is presentation; only the server
decides whether a transition is legal, and the dialog's wording ("this
cannot be undone") is only true if the server enforces it.

**How to apply:** for each transition a screen sends, drive it twice with
the same body and once from each wrong state (against the local stack, or
by reading the handler and its SQL to the predicate), with a control that
a legal different transition is refused as it should be. A wrong-state
201 is an OBSERVATION to backend-dev, never a client-side workaround; word
the dialog from their answer.

Sources (GZCoord): 01a0de5a-c3b3-7250-bb91-c846ce3c4077,
01a12596-a423-729e-a898-6cb608512c01, 01a125a4-0cbd-7984-a7c8-3f6510492b68.

*Observed 2026-10-24 (web-dev)*
