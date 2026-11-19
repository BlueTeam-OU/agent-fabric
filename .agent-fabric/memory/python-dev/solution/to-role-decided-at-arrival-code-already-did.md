---
role: "python-dev"
class: solution
topic: "to-role-decided-at-arrival-code-already-did"
description: "W11/D6 — a TO-ROLE message is not shown to a role bound after arrival; the code already did it, carrier decides at receipt, relay at first read"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7fd218d4fbfe6573
---

## W11/D6 — a TO-ROLE message is not shown to a role bound after arrival; the code already did it, carrier decides at receipt, relay at first read

j132 (PR #623, commit b994803d): D6 (owner 2026-11-15) needed no behaviour change. Carrier engine: `for_me` reads the role per message, so a late-bound role neither journals nor lists it. Relay (`gzcoord-inbox`): decided at the first READ that fetches the record, not at arrival — a record still unread when the role is bound is shown to the new holder.

**Why:** the request said to tell the owner before changing behaviour if code differed; it did not.
**How to apply:** tests/test_gzcoord_carrier_inbox.py flaked (1 FAIL, 1 timeout) when run concurrently with other work, 8/8 green run alone on base and head; run it alone before calling a failure mine. See [[same-case-red-on-two-reruns-is-not-load]].

*References: same-case-red-on-two-reruns-is-not-load*

*Anchors: `tests/test_gzcoord_carrier_engine.py::D6`, `tests/test_gzcoord_carrier_inbox.py::D6`*

*Observed 2026-11-15 (python-dev)*
