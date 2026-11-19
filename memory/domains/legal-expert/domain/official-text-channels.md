---
role: "legal-expert"
class: domain
topic: "official-text-channels"
description: "How a session reads EU and Estonian legislation when EUR-Lex or Riigi Teataja refuse automated fetches"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0ab3042aee1ed472
  - 642e2bca84113887
---

## How a session reads EU and Estonian legislation when EUR-Lex or Riigi Teataja refuse automated fetches

EUR-Lex answers curl with HTTP 202 and no text. The same official text comes from the EU Publications Office (CELLAR): `http://publications.europa.eu/resource/celex/<CELEX>` with headers `Accept: application/xhtml+xml` and `Accept-Language: eng` (used for GDPR 32016R0679 and Decision 2000/518/EC, 2026-10-15). Riigi Teataja needs JavaScript, and `moli fetch --dump markdown 'https://www.riigiteataja.ee/akt/<short name>'` (e.g. `akt/RPS`, the Accounting Act) renders it: the header gives Sõnastuse jõustumise kp, Sõnastuse kehtivuse lõpp and Avaldamismärge, the redaction to record (used for RPS § 12, 2026-11-10). Strip the `balance`/`historylink` lines it interleaves. A provider's terms read through a fetch summary are not read: quote only from the raw page (#278 review round 1). To find amendments and consolidated versions, query the CELLAR SPARQL endpoint `https://publications.europa.eu/webapi/rdf/sparql` with `cdm:resource_legal_amends_resource_legal` against the act's CELEX, and list CELEX ids starting `0<CELEX-without-sector>` for consolidations; `Accept-Language: est` returns the Estonian version (AI Act, 2026-11-09). See [[solution-carried-2026-10-18]], [[ai-act-omnibus-2026-1744]].

*References: ai-act-omnibus-2026-1744, solution-carried-2026-10-18*

*Observed 2026-11-10 (legal-expert)*
