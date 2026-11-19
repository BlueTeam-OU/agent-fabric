---
role: "rust-services-dev"
class: domain
topic: "minified-names-carry-dollar"
description: "Reading Claude Code's embedded JS by regex — a minified name can contain $, so match [\\w$]+, never \\w+"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - dbf93fc6fbeeaacc
---

## Reading Claude Code's embedded JS by regex — a minified name can contain $, so match [\w$]+, never \w+

In SPIKE-001 S36 (InterWeave j76, PR #670, 2026-11-14), s34_gate.py read 2.1.325 with `function \w+\(` and printed
`hard_skip_kinds: null`, because 2.1.325 minified that function to `$_s`. The other reads looked fine, so a null
looked like "the code changed" when only the name had. Fixed in 07a7ac729 by matching `[\w$]+` in every pattern.

**Why:** minifiers use `$` as an ordinary identifier character, and a name changes on every build.

**How to apply:** in any regex read of a bundled binary, match names as `[\w$]+` and use `(?<![\w$])` as the
boundary. Run the read on the previous build as a control, and treat a newly null field as the script's failure
until you have shown otherwise. To read "every path" statically, list each use of the object the handler is
registered with (the channel notification schema), with the guard call before each use. Related:
[[host-managed-settings-drop-mcp-config]].

*References: host-managed-settings-drop-mcp-config*

*Observed 2026-11-14 (rust-services-dev)*
