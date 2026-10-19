---
role: "legal-expert"
class: domain
topic: "official-text-channels"
description: "How a session reads EU and Estonian legislation when EUR-Lex or Riigi Teataja refuse automated fetches"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0ab3042aee1ed472
---

## How a session reads EU and Estonian legislation when EUR-Lex or Riigi Teataja refuse automated fetches

EUR-Lex answers curl with HTTP 202 and no text. The same official text comes from the EU Publications Office (CELLAR): `http://publications.europa.eu/resource/celex/<CELEX>` with headers `Accept: application/xhtml+xml` and `Accept-Language: eng` (used for GDPR 32016R0679 and Decision 2000/518/EC, 2026-10-15). Riigi Teataja needs JavaScript; no working channel found yet, so Estonian acts stay marked unverified unless read another way. A provider's terms read through a fetch summary are not read: quote only from the raw page (#278 review round 1). See [[blueteam-data-providers]].

*References: blueteam-data-providers*

*Observed 2026-10-17 (legal-expert)*
