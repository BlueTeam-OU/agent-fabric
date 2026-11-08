---
role: "language-culture"
class: workflow
topic: "supplier-review-trailer-one-line"
description: "keep the Supplier-Review trailer on one line; a wrapped one stops Kind being read as a trailer"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric-j138-reflection-pass-2026-w44-run-fabric"
derived_from:
  - 8fd14f5678411a34
---

## keep the Supplier-Review trailer on one line; a wrapped one stops Kind being read as a trailer

In j143 the commit-msg hook refused a commit for a missing kind although `Kind: work` was in the last paragraph: a `Supplier-Review:` trailer wrapped over three lines above it made git stop reading that paragraph as trailers. Keep each trailer on one line and put the detail in the body.

*Anchors: `tools/fabric/guards/commit_kind.py::every commit declares its kind in its trailers`*

*Observed 2026-11-08 (language-culture)*
