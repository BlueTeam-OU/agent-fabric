---
role: "language-culture"
class: domain
topic: "gzapi-built-in-not-based-in"
description: "gzapi.ge company copy says \"built in [redacted]\", never \"based in\", because the legal address is in Tbilisi"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - cf8e90f05ecc4a98
---

## gzapi.ge company copy says "built in [redacted]", never "based in", because the legal address is in Tbilisi

In English copy, "based in <city>" reads as the company's seat. gzapi.ge names [redacted] as where the company is from (gzapi.brand decision 0003), but the registry facts show a Tbilisi legal address. The lede therefore says "built in [redacted] and incorporated in [redacted]" (src/i18n/content.ts, content.en.company.lede at cb488dd). "Built" gives where the work happens, and "incorporated" gives the legal fact. language-culture-en read it as "yes, as it stands" (REPLY 01a1c718-4548, 2026-11-11).
**Why:** "based in [redacted]" next to "Legal address: … Tbilisi" reads as a contradiction.
**How to apply:** any new English string that places the company in a city uses a verb about the work (built, made), not "based" or "headquartered".

*Observed 2026-11-10 (language-culture)*
