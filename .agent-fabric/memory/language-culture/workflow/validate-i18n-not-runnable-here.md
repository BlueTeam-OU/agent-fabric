---
role: "language-culture"
class: workflow
topic: "validate-i18n-not-runnable-here"
description: "gzapp's validate.js runs on this account once ajv is installed in the worktree for the run; on a for/ branch only parity fails"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 511af099a247dedc
  - 5a4132622899db3d
  - 686b0dbc0c1ba968
---

## gzapp's validate.js runs on this account once ajv is installed in the worktree for the run; on a for/ branch only parity fails

On the language-culture-ge account (node present, no pnpm, no node_modules), `tools/validate_i18n/validate.js` first failed in a worktree with ERR_MODULE_NOT_FOUND (2026-10-20, 01a159b4). With ajv installed in the worktree for the run, and removed afterwards, validate.js and the selftest ran (2026-10-20, 01a15a86-df9c). The slice's "does not run here" no longer holds for this account; the web suites part is unchecked. On a single-locale for/ branch the only expected failure is key parity (the other locales lack the key yet); every other check must be clean, and the delivery says so: "only parity fails, <locales> lack <key>; selftest passes". Install ajv in the worktree, run validate.js and the selftest, then remove what you installed; any failure other than parity is yours.

*Anchors: `gzapp:tools/validate_i18n/validate.js::ajv`*

*Observed 2026-10-24 (language-culture)*
