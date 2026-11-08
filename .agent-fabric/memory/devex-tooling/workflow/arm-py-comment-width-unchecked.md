---
role: "devex-tooling"
class: workflow
topic: "arm-py-comment-width-unchecked"
description: Editing a comment in tools/fabric/github/arm.py — no lint checks line width; wrap by hand to ~118
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 91e804df725a07d2
---

## Editing a comment in tools/fabric/github/arm.py — no lint checks line width; wrap by hand to ~118

`python3 tools/fabric/lint.py --no-siblings` passes a 123-column comment line in
`tools/fabric/github/arm.py`; nothing checks width, and the file already has lines
up to 262 columns, so "max in the file" is no guide. Comment blocks there wrap at
about 118 columns (j621, commit bbb9d394, gate 4b comment).

**Why:** a qualifier inserted mid-paragraph pushed the tail over; only an awk
length check caught it.

**How to apply:** after a comment edit, `awk 'NR>=a&&NR<=b{print length}'` over
the block and rewrap anything past ~118; see [[scripted-edit-anchor-on-block]].

*References: scripted-edit-anchor-on-block*

*Anchors: `tools/fabric/github/arm.py::# 4b. the review engines the policy requires`*

*Observed 2026-11-07 (devex-tooling)*
