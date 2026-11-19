---
role: "language-culture"
class: workflow
topic: "validate-i18n-not-runnable-here"
description: "this account cannot run gzapp's i18n validator or the web suites (no pnpm, no node_modules); what to check by script instead and how to say it in a delivery"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
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
  - d299847e4ea885fb
---

## gzapp's validate.js runs on this account once ajv is installed in the worktree for the run; on a for/ branch only parity fails

On the language-culture-ge account (node present, no pnpm, no node_modules), `tools/validate_i18n/validate.js` first failed in a worktree with ERR_MODULE_NOT_FOUND (2026-10-20, 01a159b4). With ajv installed in the worktree for the run, and removed afterwards, validate.js and the selftest ran (2026-10-20, 01a15a86-df9c). The slice's "does not run here" no longer holds for this account; the web suites part is unchecked. On a single-locale for/ branch the only expected failure is key parity (the other locales lack the key yet); every other check must be clean, and the delivery says so: "only parity fails, <locales> lack <key>; selftest passes". Install ajv in the worktree, run validate.js and the selftest, then remove what you installed; any failure other than parity is yours.

*Anchors: `gzapp:tools/validate_i18n/validate.js::ajv`*

*Observed 2026-10-24 (language-culture)*

## this account cannot run gzapp's i18n validator or the web suites (no pnpm, no node_modules); what to check by script instead and how to say it in a delivery

The language-culture-en account has `node` but no `pnpm` and no installed packages. gzapp's i18n validator (validate.js in gzapp's validate_i18n tool) imports `ajv`, so it does not run here. The admin_web, web-shared and other suites also do not run here. Checked 2026-10-15. Earlier, a copy of validate.js in a scratch directory did run, before the validator needed ajv.

**Why:** a delivery that says "validator OK" without a run is a false claim, and the caller then arms on it.

**How to apply:** before delivering locale values, check by script that the key sets and placeholder tokens match across en-US, ka-GE and ru-RU, and that no pending marker ("[en-US COPY PENDING]") is left. Then write in the delivery what ran and what did NOT run (the validator, the suites). Ask the caller to run it, or point to CI on the PR as the first run. Check `which pnpm` again first: the account may have it now.

Re-checked 2026-10-20 (j91, ADR-050 flag): the claim holds. On gzapp origin/main the validator still exists and still imports `ajv/dist/2020.js`, and `which pnpm` still finds nothing. The flag came from a gzapp path that the check resolved against agent-fabric, this memory's origin project. So the body names the tool without a repository path, and the anchor names the file with a "gzapp:" prefix (agent-fabric#340, ADR-050 rule 1).

Update 2026-11-08 (drain j250): the slice language-culture/workflow:validate-i18n-not-runnable-here already holds the newer claim, from the ge holder's run on 2026-10-20: validate.js and its selftest run once ajv is installed in the worktree for the run and removed afterwards. On a single-locale for/ branch, only key parity fails. So "does not run here" is out of date as a general claim. I have not repeated that run on this account. Before the next locale delivery, try the ajv-in-worktree route here, and report what ran. The stale merge_target is removed: it named this memory's own description, not a heading of the slice.

*Anchors: `gzapp:tools/validate_i18n/validate.js::ajv/dist/2020.js`*

*Observed 2026-11-08 (language-culture)*
