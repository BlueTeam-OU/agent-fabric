---
role: "fabric-coordinator"
class: domain
topic: "locale-suffixes"
description: "The fabric's locale suffixes: ge is Georgian (language-culture-ge, script Georgian), ru Russian; German would be de — never read ge as German"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - d8d2c8ca090f2931
---

## The fabric's locale suffixes: ge is Georgian (language-culture-ge, script Georgian), ru Russian; German would be de — never read ge as German

`identities/roles/language-culture/locale/ge/` is the **Georgian**
locale, held by `language-culture-ge` (the product's Georgian brand
string is გზაპი; its notes are in Georgian script). `ru` is Russian.
A German locale, if one is ever added, is `de`. The suffixes are the
holders' own choice and do not follow ISO 639-1 for Georgian (which
would be `ka`).

**Why:** the owner corrected "georgian not german; german is de" on
2026-09-19 — the suffix invites the wrong reading.

**How to apply:** write "the ge (Georgian) holder" the first time a
message or note names the locale; never expand `ge` to German.

*Observed 2026-09-19 (fabric-coordinator)*
