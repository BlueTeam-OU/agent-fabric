---
role: "devex-tooling"
class: domain
description: "Claude/Anthropic GitHub Actions installed via /install-github-app bill the subscription"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-08-10"
origin:
  - clone_id: "clone-c8407dca40bd40fc"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 13207c2df7e3d060
  - 5783d4d4135a727b
  - 7cf67bbefe79aa12
  - e5421b428888d1af
  - ff67e1fe1f0cb9f9
---

## Claude/Anthropic GitHub Actions installed via /install-github-app bill the subscription

The two workflows added by the Claude Code GitHub app install (a PR-assistant workflow and a code-review workflow) authenticate via an OAuth token that is a subscription-allowance credential, not a metered API key — so every triggered run draws down the same interactive usage quota as the person's own Claude Code sessions, with no separate CI budget. The review workflow in particular triggers on every push to any open PR; without an explicit concurrency group, that fired 17 times in about 50 minutes across a handful of parallel session branches, with one run alone costing several dollars for zero actual review output (the run had shallow git history so it had nothing to diff against, plus no tool allowlist, which caused dozens of internal permission denials per run). Before enabling any such workflow: confirm which credential it authenticates with, get explicit consent if it's a subscription token rather than an API key, and give any PR-push-triggered workflow a concurrency group. The fix here was to disable it at the runtime level, delete the workflow files, and delete the leftover OAuth secret — all three, since disabling alone leaves the files and credential live for a future accidental re-trigger.
