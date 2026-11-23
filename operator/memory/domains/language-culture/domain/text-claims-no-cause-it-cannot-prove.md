---
role: "language-culture"
class: domain
topic: "text-claims-no-cause-it-cannot-prove"
description: "a failure, refusal or state text names a cause, a quality or a property only where the code proves it; otherwise \"might have\", or no cause"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ab06743c95cb49f9
---

## a failure, refusal or state text names a cause, a quality or a property only where the code proves it; otherwise "might have", or no cause

A text that explains a failure is read as the reason for it. When the
app cannot know the reason, a stated cause is a false statement, even if
it is the likely cause. Five cases in four days (W43):
- InterWeave "superseded" refusals said another program changed the
  address "and that change was kept". The runtime also refuses where no
  other change was made, so all four texts became "might have changed".
- gzapp `stopped-reporting` said the vehicle stopped reporting. A row
  leaves the list for other reasons, which the page cannot tell apart.
  The key became `gone-from-positions`, with no cause. The list heading
  "Vehicles reporting" was false in the same way: the list also holds
  stale vehicles. It became "Vehicles".
- KeyNewerVersion could say only that a newer version *may* use the
  key. Then "To keep this key, update" contradicted that "may", so it
  became "To try to keep the key".
- ImageUnreadable named PNG or JPEG, a type the file already had. That
  reads as "you picked the wrong type": a false cause, and close to
  blame.
- `official_stop_selected`: "a better stop" claimed a quality that the
  driver cannot check. "chosen over the planned one" says what the
  system did.

**Why:** a cause in a request or a draft is often the writer's guess.
Twice the review found it in a text I had already finalised (I took the
trigger from the request and did not check the list's rules).

**How to apply:** for each "because", "so", "stopped", "changed",
"better", and each list name that claims a property, ask whether the
code proves it in every case that shows the text. If it does not, say
what happened and not why, or use "might have". Then check that the next
sentence does not promise what the "might" left open.

Related: [[key-value-true-in-every-state]]

*References: key-value-true-in-every-state*

*Observed 2026-10-25 (language-culture)*
