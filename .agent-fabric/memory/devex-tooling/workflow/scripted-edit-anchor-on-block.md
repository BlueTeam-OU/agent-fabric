---
role: "devex-tooling"
class: workflow
topic: "scripted-edit-anchor-on-block"
description: A scripted str.replace/index edit of a workflow or config file must anchor on the enclosing block and assert one match — duplicated comments land the edit in the wrong block
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 006c8c7cb416b263
---

## A scripted str.replace/index edit of a workflow or config file must anchor on the enclosing block and assert one match — duplicated comments land the edit in the wrong block

gzapp #1126 review F1 (P2): ci.yml's `contracts:` and `api_surface:` paths filters carry the
same "The lockfile is an INPUT to this job" paragraph and the same `- 'pnpm-lock.yaml'`
line. A Python edit using `t.index(<paragraph>)` took the first, in `contracts`, and silently
un-gated the contracts job for lockfile-only PRs, while `api_surface` stayed unchanged.
actionlint, zizmor and all 108 guards passed it; only the blind review caught it.

**Why:** in a YAML file, duplicated text is the norm, not an exception, and a filter change
passes every syntax check.
**How to apply:** slice to the named block first (`t.index("            api_surface:\n")`
up to the next sibling key), edit inside that slice, and `assert slice.count(old) == 1`.
Afterwards, diff the parsed filter lists per block at base and head, not the text.

*Anchors: `.github/workflows/ci.yml::api_surface:`*

*Observed 2026-10-19 (devex-tooling)*
