---
role: "fabric-coordinator"
class: threads
topic: "assemble-hygiene-inconsistent"
description: "assemble substitutes a banned term in place on both paths; only non-English prose is refused; code in tools/fabric/assembler/"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
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
  - e45c8f8d1bdb5f6b
---

## assemble substitutes a banned term in place on both paths; only non-English prose is refused; code in tools/fabric/assembler/

The assembler substitutes a banned term in place on both paths: `hygiene_substitute` (tools/fabric/assembler/core.py) runs on a new claim's title, description, body and topic and on carried text, and each substitution is named under "REDACTED (hygiene ...)". The one remaining asymmetry is non-English prose: a new claim with it is refused and not written, a carried slice with it is rewritten as it was and the run exits 1.

`test_carried_text_is_redacted_the_same_way_a_claim_is` (tests/test_assemble.py) pins carried-text substitution. Read the REDACTED lines of a run; a red run on non-English carried text means translating the slice in place. Related: [[assemble-not-idempotent-over-same-drain]].

*References: assemble-not-idempotent-over-same-drain*

*Observed 2026-10-10 (fabric-coordinator)*
