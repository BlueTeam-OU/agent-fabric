---
role: "web-dev"
class: domain
topic: "refusal-copy-names-the-rule-not-a-cause"
description: "When a page shows a server refusal, a withheld value or a disappearance the client cannot explain: the state and its copy name the rule or limits, never a cause the client guessed"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0fee3be2b1bb35f2
---

## When a page shows a server refusal, a withheld value or a disappearance the client cannot explain: the state and its copy name the rule or limits, never a cause the client guessed

A server refusal, a withheld value or an item that disappeared often
has more than one possible cause, and the client is not told which one
applies. Three times in one week a meaning note or a state named a cause
the client could not know, and each time the copy was corrected to
state the rule instead:

- A period was refused with a 400. It may not have closed yet, or it may
  be older than the window and was never rolled up. The copy now states
  both limits and "outside those limits". It does not say which one.
- A partition was hidden by k-suppression. My note said "a part has
  fewer than k", but a partition is also withheld because of its parent
  count or an intersection. The copy now says "Hidden by the rule on
  counts below {k}".
- A vehicle left a live list. The line names no cause, only that it left
  the list.

Related: [[repeat-a-transition-to-test-the-server-guard]], since the
server's answer is the refusal.

**How to apply:** when you write the meaning note for a locale request,
describe the rule and every cause that is possible, and do not give one
cause as if it were the reason. Do not branch the UI on a cause you
inferred (for example "not closed yet" because of the browser clock).
Render one refused state, and offer a way out such as going to the
newest valid item. If the person needs to know the cause, ask
backend-dev to serve it. Do not derive it on the client.

Verified on gzapi-org/gzapp main, 2026-10-31: en-US
admin.stops.shadow-evidence.refused-description and .not-shown-note.

Sources (GZCoord): 01a1790f-0425-7eb9-a133-bb82e41b9971,
01a17619-4449-7d72-be8e-51de17361e86, 01a17dc8-3466-7671-b3f5-1aa7dbcace76.

*References: repeat-a-transition-to-test-the-server-guard*

*Observed 2026-10-31 (web-dev)*
