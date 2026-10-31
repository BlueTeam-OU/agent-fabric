---
role: "devex-tooling"
class: domain
topic: "gh-merge-fails-but-merges"
description: "gh pr merge can exit non-zero while GitHub merges the PR, and the PR API then lags (OPEN, DIRTY) for minutes; ask git whether the head is in the base"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4da07b71f14b8bf1
---

## gh pr merge can exit non-zero while GitHub merges the PR, and the PR API then lags (OPEN, DIRTY) for minutes; ask git whether the head is in the base

On a CLEAN PR with every check finished, `gh pr merge --auto` has exited non-zero ("merge already in
progress") while GitHub merged the PR (gateway #33 2026-10-10, agent-fabric #237 2026-10-13). For minutes
after, the PR API read OPEN, then CONFLICTING/DIRTY, while the merge commit was already on origin/main.
A tool that judges by the API calls a merged PR blocked. The fix (agent-fabric branch
for/user/arm-merged-readback, tools/fabric/github/landed.py): fetch the base and run
`merge-base --is-ancestor <head> origin/<base>`. Only a yes is acted on. A squash or rebase merge never
makes the head an ancestor, so for those the API's answer stands.

*Observed 2026-10-13 (devex-tooling)*
