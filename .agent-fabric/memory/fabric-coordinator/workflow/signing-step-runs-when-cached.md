---
role: "fabric-coordinator"
class: workflow
topic: "signing-step-runs-when-cached"
description: "new-agent step 11 (shared signing key into a new account) can run from my session when gpg-agent has the key's passphrase cached; check before handing the owner a terminal step"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c4aec9068192acd7
---

## new-agent step 11 (shared signing key into a new account) can run from my session when gpg-agent has the key's passphrase cached; check before handing the owner a terminal step

2026-10-16: three legal-expert logins could not sign (step 11 skipped: no terminal). Before
handing the owner the passphrase step I ran `gpg-connect-agent 'keyinfo --list' /bye`: both
keygrips of user.signingkey showed `C` (cached), so calling
`provisioning.signing.signing_key(<login>, "develop-qzapp")` from my session exported, imported,
trusted and test-signed for all three with no pinentry. (`new-agent.sh --signing-key-only`
refuses without a terminal even when cached.)

**Why:** the owner asked "do it you"; the step needs the passphrase only when the cache is cold.
**How to apply:** check the agent cache first; cached → run signing_key directly; cold → the
owner runs `--signing-key-only <login>` at a terminal. The GitHub key registration still needs
`gh auth refresh -s admin:ssh_signing_key`, a browser sign-in only the owner can do.

*Observed 2026-10-15 (fabric-coordinator)*
