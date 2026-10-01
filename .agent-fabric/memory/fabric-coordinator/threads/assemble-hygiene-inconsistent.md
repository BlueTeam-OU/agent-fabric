---
role: "fabric-coordinator"
class: threads
topic: "assemble-hygiene-inconsistent"
description: "CLOSED 2026-09-20: assemble substitutes a banned term in place on both paths (new claim and carried text) since the 2026-09-16 decision; only non-English prose is still refused in a claim and reported in carried text — both make the run…"
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
  - 4650184628f63f65
---

## CLOSED 2026-09-20: assemble substitutes a banned term in place on both paths (new claim and carried text) since the 2026-09-16 decision; only non-English prose is still refused in a claim and reported in carried text — both make the run red; a test pins carried-text substitution

**Closed 2026-09-20.** The 2026-09-16 observation (a city name rejected
from one path and admitted from the other) predates the same day's
decision to substitute in place: `hygiene_substitute` now runs on a new
claim's title, description, body and topic, and on carried text, with
each substitution named under "REDACTED (hygiene …)". The remaining
asymmetry is non-English prose only — a new claim with it is refused and
not written, a carried slice with it is rewritten as it was and the run
exits 1 — and neither admits anything new. Pinned by
`test_carried_text_is_redacted_the_same_way_a_claim_is` (agent-fabric,
the assembler branch of 2026-09-20). Related:
[[assemble-not-idempotent-over-same-drain]].

*References: assemble-not-idempotent-over-same-drain*

*Observed 2026-09-16 (fabric-coordinator)*
