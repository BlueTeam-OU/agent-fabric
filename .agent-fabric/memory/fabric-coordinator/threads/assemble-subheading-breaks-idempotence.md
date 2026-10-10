---
role: "fabric-coordinator"
class: threads
topic: "assemble-subheading-breaks-idempotence"
description: "A claim body's own ## headings are demoted at render time and old split slices absorbed; code in tools/fabric/assembler/"
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
  - c3a8ccb9eb0b71b1
  - c83381f8ea5b41b3
  - f528b0b9346eb0b8
---

## A claim body's own ## headings are demoted at render time and old split slices absorbed; code in tools/fabric/assembler/

A claim body's own `## ` lines are demoted at render time (`demote_headings`, tools/fabric/assembler/slices.py), and old slices already split at such headings are absorbed back (`absorbed`, same file; `existing_sections` in targets.py reads the slice's sections). Pinned by `test_a_claim_body_s_own_headings_never_open_a_section` in tests/test_assemble.py.

**How to apply:** re-check a thread against the tree before citing it as open; this one stayed marked open after its fix and misled a review. To test any assembler change, run one bundle twice and compare the tree byte for byte. See [[assemble-not-idempotent-over-same-drain]].

*References: assemble-not-idempotent-over-same-drain*

*Observed 2026-10-10 (fabric-coordinator)*
