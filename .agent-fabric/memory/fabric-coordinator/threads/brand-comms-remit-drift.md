---
role: "fabric-coordinator"
class: threads
topic: "brand-comms-remit-drift"
description: "gzapp.decks brand-comms remit lags AGENTS.md; check it against origin/main AGENTS.md whenever a repo rule changes"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8513b5af9338c517
---

## gzapp.decks brand-comms remit lags AGENTS.md; check it against origin/main AGENTS.md whenever a repo rule changes

The gzapp.decks remit `.agent-fabric/roles/brand-comms.md` has drifted from
`AGENTS.md` twice: script names (.mjs → Python, a4dca79) and the language
rule ("Bilingual, English primary" → one deck per language, 28a5c7a), both
on PR #29 (2026-10-28). Still open: its "Read first" line points at the
site's `src/styles/global.css` for tokens, though the remit itself says
gzapi.brand is the authority (brand/decisions/0001). Related:
[[remit-names-scripts-by-stem]].

*References: remit-names-scripts-by-stem*

*Observed 2026-10-28 (fabric-coordinator)*
