---
role: "devex-tooling"
class: domain
topic: "sudo-i-leaves-dollar-live-in-the-target-shell"
description: "sudo -i with a command re-escapes the argv for the target login shell but leaves $ unescaped, so any \"$1\"/\"$VAR\" in the command expands in that shell (empty) — never pass a $-bearing argument under -i."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 6945ca3f6784fffe
  - 891a2c06cfd929d8
---

## correction — the sudo -i $-expansion example came from a project provisioning doc, not the fabric tree; the rule itself stands

`sudo -i <cmd>` re-escapes the argv for the target login shell but leaves `$` unescaped. So a `"$1"` or `"$VAR"` in the command expands in that shell, usually to nothing. Never pass a `$`-bearing argument under `-i`: expand it in the caller and pass the value, or use absolute paths and an option such as `--workspace`.

The rule comes from sudo's own escaping, not from any one document. The example that taught it was in a managed project's provisioning guide; the fabric's provisioning is now Python (`tools/fabric/provisioning/`).

*Observed 2026-10-10 (devex-tooling)*
