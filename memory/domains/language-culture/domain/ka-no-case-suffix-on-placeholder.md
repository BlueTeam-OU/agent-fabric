---
role: "language-culture"
class: domain
topic: "ka-no-case-suffix-on-placeholder"
description: "no case suffix on a placeholder ({sender}, {id}) — build the sentence so it stands in the nominative or in brackets"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bf4fe272568fcc7f
---

## no case suffix on a placeholder ({sender}, {id}) — build the sentence so it stands in the nominative or in brackets

A placeholder ({sender}, {from}, {id}) in a Georgian string can't take a case suffix: an address (develop-qzapp/x) or an id doesn't decline, and "{sender}-ის" either breaks in the terminal or confuses the reader. Build the sentence so the placeholder stands in the nominative ("the address is {sender}", "shown as sender: {sender}") or in brackets beside its noun ("the relay copy ({id})"). Seen 2026-10-24, j119, agent-fabric ka-GE.json, commit 0f70648e.

*References: first-pass-fix-needs-source*

*Observed 2026-10-24 (language-culture)*
