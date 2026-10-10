---
role: "python-dev"
class: workflow
topic: "git-signing-key-for-agent-accounts"
description: "python-dev-03's commits failed 'No secret key' until the owner provided the signing key; push needs the gh credential helper"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0ccf869f476c2977
---

## python-dev-03's commits failed 'No secret key' until the owner provided the signing key; push needs the gh credential helper

On a new agent account git is configured (~/.gitconfig) to sign with the owner's key; a commit fails `gpg: skipped ... No secret key` until the owner provides it (asked, not bypassed — never switch to unsigned or the account's own subkey unasked). `git push` over https has no credential helper: use `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`. Hooks also refuse commits to coordinator-owned paths (authority.json excluding) — revert those edits and list the sites for the coordinator.

*Observed 2026-10-08 (python-dev)*
