---
role: "fabric-coordinator"
class: solution
topic: "assemble-not-idempotent-over-same-drain"
description: "FIXED 2026-09-20: assemble is idempotent over the same drain — split_by_budget no longer counts a re-rendered claim twice (heading+text identity); the -2 copies of 2026-09-17 were the carried count doubling past half budget"
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
  - d3fb6e07f8cf8607
---

## FIXED 2026-09-20: assemble is idempotent over the same drain — split_by_budget no longer counts a re-rendered claim twice (heading+text identity); the -2 copies of 2026-09-17 were the carried count doubling past half budget

On 2026-09-17, assembling the same drain twice into InterWeave's
`.agent-fabric/memory/p2p-network-dev/` (to pick up a brief added
after the first run) produced `-2` copies of eight slices, a stray
`threads/` directory and a rewritten
`memory/domains/p2p-network-dev/domain/autonat-client-crate-facts.md`
in agent-fabric with a generic description; lint then reported the
index drifted.

**Why:** the assembler merges incoming claims against the slices already
present and treats the same claim as a second source rather than the
same one.

**Fixed 2026-09-20** (agent-fabric, the assembler branch): `carried_chars` excludes a carried section that is one of this drain's claims re-rendered (same heading and text — write_slice's own no-op rule), so the budget is no longer counted twice and a second assemble is byte-identical; `test_output_is_byte_stable` is sized past half budget and checks the file set. **Before that:** one drain, one assemble. To add a hand-authored entry
(charter, brief, recall) afterwards, edit `INDEX.md` in the assembler's
line format; to re-assemble, `git checkout -- .agent-fabric/memory`
(and `memory/domains/<role>/` in the fabric) first. A fix to the tool
belongs with [[assemble-hygiene-inconsistent]].

*References: assemble-hygiene-inconsistent*

*Observed 2026-09-17 (fabric-coordinator)*
