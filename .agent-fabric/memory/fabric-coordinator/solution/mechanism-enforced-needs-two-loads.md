---
role: "fabric-coordinator"
class: solution
topic: "mechanism-enforced-needs-two-loads"
description: "marking a policies/mechanisms.json entry enforced — lint refuses it unless a lint rule AND the pre-commit hook load the checker"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9e90fbe4247ed606
---

## marking a policies/mechanisms.json entry enforced — lint refuses it unless a lint rule AND the pre-commit hook load the checker

ADR-067's catalogue (`policies/mechanisms.json`, #511, j674) is checked by `tools/fabric/lint_rules/mechanisms.py`.
An `enforced` entry passes only when its checker's module stem is loaded by some `tools/fabric/lint_rules/*.py`
(`_load("<stem>")` or `import <stem>`) and by `tools/fabric/guards/commit_hooks.py` (`import <stem>`); a mention in a
comment does not count. So wiring a Wave 1 checker is three edits in one commit: the lint rule, the hook's
`_check_<x>` in `pre_commit`, and the status flip — then its suite case. `pending` needs `job: <login>/j<n>`,
`planned` needs `waits_on`. Related: [[review-and-guards]].

*References: review-and-guards*

*Anchors: `tools/fabric/lint_rules/mechanisms.py::_loads`, `policies/mechanisms.json`*

*Observed 2026-11-08 (fabric-coordinator)*
