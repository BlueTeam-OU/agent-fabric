---
role: "fabric-coordinator"
class: workflow
topic: "locale-codes-say-the-language"
description: "In prose to the owner name the language (Georgian, Russian), never the locale code alone; \"ge\" was read as German (2026-10-24)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - aa46f63be2160c6f
---

## In prose to the owner name the language (Georgian, Russian), never the locale code alone; "ge" was read as German (2026-10-24)

The fabric's locale directories are `ge` (Georgian, ka-GE), `ru` (Russian),
`en`. On 2026-10-24 my messages and PR #371's title said "legal-expert ge
copy" and the owner read German.

**Why:** `ge` is the country code of [redacted], not a language code; readers
outside the tree pattern-match it to German.

**How to apply:** write "Georgian (ka-GE)" or "Russian" in anything a person
reads (messages, PR titles and bodies, memory); the code alone only in a path.

*Observed 2026-10-24 (fabric-coordinator)*
