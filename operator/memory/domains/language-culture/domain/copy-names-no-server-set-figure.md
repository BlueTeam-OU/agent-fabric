---
role: "language-culture"
class: domain
topic: "copy-names-no-server-set-figure"
description: "a time the server sets (a verification's expiry and the like) is not stated as a number in copy"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 8720a5457a88ff93
---

## a time the server sets (a verification's expiry and the like) is not stated as a number in copy

When the server sets a value (for example the lifetime of a step-up verification, "about five minutes"), the copy does not state it as a number and speaks of the event instead: «Когда подтверждение истечёт, код спросят снова» ("when the verification expires, the code will be asked again"). A number in the dictionary goes false as soon as the server changes it. Example: admin.step-up.note, commit 6633fbafd (j72). In the same place, «действие будет выполнено» ("the action will be carried out"), not «повторится» ("will repeat"): for an action on personal data, "will repeat" reads as running it a second time.

**Why:** the second pass against en-US 45325bd38, 2026-10-20.
**How to apply:** any time or limit from the server's configuration is named in the text as an event, not as a number.

*Observed 2026-11-09 (language-culture)*
