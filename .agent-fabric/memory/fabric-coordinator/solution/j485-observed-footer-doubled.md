---
role: "fabric-coordinator"
class: solution
topic: "j485-observed-footer-doubled"
description: "assembler claim_block doubles a body's own *Observed* footer (gzapp#1197) — contract sent to python-dev-04 2026-10-31"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 36690a2eb2cf5bc3
---

## assembler claim_block doubles a body's own *Observed* footer (gzapp#1197) — contract sent to python-dev-04 2026-10-31

claim_block (tools/fabric/assembler/slices.py:426, origin/main d4105b85) appends `*Observed <date> (<role>)*` whenever observed_at is set and never strips one already at the end of the body. A memory whose body carries the footer (a correction memory, or one copied from a slice) therefore gets two. Seen in gzapi-org/gzapp#1197 (the drain of 2026-10-28): the two architect-cto workflow/correction-*.md sections each end with the same footer twice.

Contract: strip the trailing OBSERVED_RE matches from the body. The claim's own footer wins; with no observed_at, the body's last footer is kept once. Sent as REQUEST 01a190bb-8626 (seq 692250) to python-dev-04 as an extra commit on their j481 for/ branch ([[j481-assembler-same-run-claims]]). After the next gzapp drain, check that the doubled sections render with a single footer.

*References: j481-assembler-same-run-claims*

*Anchors: `tools/fabric/assembler/slices.py::claim_block`*

*Observed 2026-10-31 (fabric-coordinator)*
