---
role: "python-dev"
class: workflow
topic: "memory-anchors-plain-literals"
description: memory anchors that the drain holds back — use a plain identifier that is a literal substring of the file, not a quoted or subscripted expression
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9c33c4f4c5854f16
---

## memory anchors that the drain holds back — use a plain identifier that is a literal substring of the file, not a quoted or subscripted expression

The weekly drain holds a claim back when its `anchors:` entry `path::literal` is not a literal substring of the file at origin/main (2026-10-31 drain, #444, REQUEST 01a1968e). Two of mine were held: `records.py::fields["worktree"]` (the code reads `fields.get("worktree")`) and `verbs.py::args.cmd == "retract"` (the drain report shows the quotes stripped, so the literal no longer matched).

**Why:** the anchor is checked as text, so a rewrite of the expression or any quote character in it makes a still-true fact look moved.
**How to apply:** anchor on a bare identifier or call that appears verbatim (`verbs.py::retract`, `settle.py::checkout_of`); before saving, `git grep -c '<literal>' origin/main -- <path>` must be non-zero. When a REQUEST names held anchors, check the claim against the tree first, then change only the anchor if the fact still holds.

*Anchors: `tools/fabric/jobsparts/verbs.py::retract`*

*Observed 2026-11-01 (python-dev)*
