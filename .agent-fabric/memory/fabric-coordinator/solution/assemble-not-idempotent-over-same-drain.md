---
role: "fabric-coordinator"
class: solution
topic: "assemble-not-idempotent-over-same-drain"
description: assemble is idempotent over the same drain; the code is in tools/fabric/assembler/
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
  - 4c44cb4e78524ec3
  - d3fb6e07f8cf8607
---

## assemble is idempotent over the same drain; the code is in tools/fabric/assembler/

Assembling the same drain twice is byte-stable: `carried_chars` excludes a carried section that is one of this drain's claims re-rendered (same heading and text), so `split_by_budget` never counts it twice and no `-2` copies appear. The code is in `tools/fabric/assembler/` (`carried_chars`, `split_by_budget` in writer.py; `tools/fabric/assemble.py` is only the entry point); `tests/test_assemble.py` holds `test_output_is_byte_stable`, sized past half budget, and checks the file set.

**How to apply:** a re-assemble is safe, but a hand-authored entry (charter, brief, recall) added afterwards still goes into `INDEX.md` in the assembler's line format. If a run leaves stray copies, suspect the budget count first. See [[assemble-hygiene-inconsistent]].

*References: assemble-hygiene-inconsistent*

*Observed 2026-10-10 (fabric-coordinator)*
