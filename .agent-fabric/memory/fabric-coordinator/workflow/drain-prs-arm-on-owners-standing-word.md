---
role: "fabric-coordinator"
class: workflow
topic: "drain-prs-arm-on-owners-standing-word"
description: "memory-drain PRs (any project's half or the fabric half) may be armed under the work-commit minimum on the owner's standing word"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 38c886d939582c00
---

## memory-drain PRs (any project's half or the fabric half) may be armed under the work-commit minimum on the owner's standing word

The owner, 2026-11-02 (session of j500, after gzapi.ge #27): "I authorize you to merge all memory drain even if you're under 8 rule." A drain PR still gets its blind review and clean lint first; only the work-commit minimum is waived. `fabric-pr arm <n> --basis "the owner's word (standing, 2026-11-02, memory drains): …"`.

**Why:** a drain half is typically 1–3 work commits, so every one stalled waiting for a per-PR "arm <n>".

**How to apply:** only for PRs whose change is a memory drain (`.agent-fabric/memory/` or `memory/` assembled output, retirements); any other PR under the minimum still needs its own word. Related: [[publish-requires-doppler-secrets]].

*References: publish-requires-doppler-secrets*

*Anchors: `tools/fabric/github/arm.py::owner's word`*

*Observed 2026-11-02 (fabric-coordinator)*
