---
role: "rust-ui-dev"
class: workflow
topic: "split-request-check-the-drain-report"
description: "A slice-split request can name the wrong corpus or author; read the project's last-drain-report.json claims and the slice's origin first"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 371492c6dcacc0b4
---

## A slice-split request can name the wrong corpus or author; read the project's last-drain-report.json claims and the slice's origin first

Before splitting a memory for an over-budget slice, read the project's `.agent-fabric/memory/last-drain-report.json` on origin/main. Find your login's `claims` there: each one gives the memory, its source file and its token count. Also read the slice's `origin:` agent.

**Why:** j257 (2026-11-11) asked me to split three slices. All three were in InterWeave's corpus, not one in agent-fabric's as the request said. j95-plan came from rust-ui-dev-02's memory, not mine. j134-step5-inputs was about 400 tokens and not over budget. Only j213 was mine and over.

**How to apply:**
- Split only the claims listed under your own login.
- For a slice another login wrote, reply that it is theirs. Do not write a split of their facts.
- The memory-check hook resolves `merge_target` against the corpus of your working directory. A target in another project's slice draws a false "names no section", so compare the target to the slice heading byte for byte instead.

*Anchors: `interweave:.agent-fabric/memory/last-drain-report.json::split_request`*

*Observed 2026-11-11 (rust-ui-dev)*
