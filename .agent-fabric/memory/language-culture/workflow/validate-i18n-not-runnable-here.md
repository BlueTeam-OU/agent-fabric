---
role: "language-culture"
class: workflow
topic: "validate-i18n-not-runnable-here"
description: "this account cannot run gzapp's i18n validator or the web suites (no pnpm, no node_modules); what to check by script instead and how to say it in a delivery"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-en"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5a4132622899db3d
---

## this account cannot run gzapp's i18n validator or the web suites (no pnpm, no node_modules); what to check by script instead and how to say it in a delivery

The language-culture-en account has `node` but no `pnpm` and no installed packages. gzapp's `tools/validate_i18n/validate.js` imports `ajv`, so it does not run here. The admin_web, web-shared and other suites also do not run here. Checked 2026-10-15. Earlier, a copy of validate.js in a scratch directory did run, before the validator needed ajv.

**Why:** a delivery that says "validator OK" without a run is a false claim, and the caller then arms on it.

**How to apply:** before delivering locale values, check by script that the key sets and placeholder tokens match across en-US, ka-GE and ru-RU, and that no pending marker ("[en-US COPY PENDING]") is left. Then write in the delivery what ran and what did NOT run (the validator, the suites). Ask the caller to run it, or point to CI on the PR as the first run. Check `which pnpm` again first: the account may have it now.

*Observed 2026-10-15 (language-culture)*
