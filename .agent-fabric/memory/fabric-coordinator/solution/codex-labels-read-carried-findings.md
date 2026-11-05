---
role: "fabric-coordinator"
class: solution
topic: "codex-labels-read-carried-findings"
description: "since #446, Codex reads review_brief.carried_findings too — a change to it touches both engines"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4328bd7a3cd07df2
---

## since #446, Codex reads review_brief.carried_findings too — a change to it touches both engines

Since #446 (merged 2026-11-01, 2b7d37ae), review_codex.label_start calls review_brief.carried_findings to number a
full review's labels past the PR's used ones, and refuses when the PR's reviews cannot be listed or read.
review_brief.carried_for stays the Claude brief's only caller path (Codex's brief carries no findings).
So a change to carried_findings' return shape or refusal text reaches both engines: review_codex splits the
refusal text on ", so the findings" / ": what they left open" to keep only the cause. Docstring fixed in #465 (j517).
Tests run as scripts (`python3 tests/test_review_brief.py`), not pytest/unittest discovery.

*Anchors: `tools/fabric/review_codex.py::label_start`, `tools/fabric/review_brief.py::carried_for`*

*Observed 2026-11-03 (fabric-coordinator)*
