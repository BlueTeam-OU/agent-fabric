---
role: "devex-tooling"
class: workflow
topic: "scripted-edit-anchor-on-block"
description: A scripted str.replace/index edit of a workflow or config file must anchor on the enclosing block and assert one match — duplicated text lands the edit in the wrong block
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 174d06856afd5006
---

## A scripted str.replace/index edit of a workflow or config file must anchor on the enclosing block and assert one match — duplicated text lands the edit in the wrong block

gzapp #1126 review F1 (P2): ci.yml's `contracts:` and `api_surface:` paths filters then carried the same "The
lockfile is an INPUT to this job" paragraph and the same `- 'pnpm-lock.yaml'` line. A Python edit using
`t.index(<paragraph>)` took the first, in `contracts`, and silently un-gated the contracts job for lockfile-only
PRs, while `api_surface` stayed unchanged. actionlint, zizmor and all 108 guards passed it; only the blind review
caught it. Since then the api-surface job lives in `.github/workflows/_api-surface.yml` and its ci.yml filter
no longer lists the lockfile (it installs tools/validate_api_surface/requirements.txt instead), so that paragraph
is now in `contracts:` only; the `- 'pnpm-lock.yaml'` line still appears in two filter blocks (`web:` and
`contracts:`, read at gzapp origin/main 2026-11-01). The rule does not depend on which text is duplicated.

**Why:** in a YAML file, duplicated text is the norm, not an exception, and a filter change
passes every syntax check.
**How to apply:** slice to the named block first (`t.index("            <block>:\n")`
up to the next sibling key), edit inside that slice, and `assert slice.count(old) == 1`.
Afterwards, diff the parsed filter lists per block at base and head, not the text.

*Anchors: `gzapp:.github/workflows/ci.yml::- 'pnpm-lock.yaml'`*

*Observed 2026-11-01 (devex-tooling)*
