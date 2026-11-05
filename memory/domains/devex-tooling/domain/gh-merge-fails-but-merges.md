---
role: "devex-tooling"
class: domain
topic: "gh-merge-fails-but-merges"
description: "GitHub's API lags its own writes: gh pr merge can exit non-zero while the PR merges and the PR reads OPEN/DIRTY for minutes; a repo PATCH reads back unchanged for seconds; ask git, or retry the read with backoff, before calling a write…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4da07b71f14b8bf1
  - e788bf57e0b56849
---

## GitHub's API lags its own writes: gh pr merge can exit non-zero while the PR merges and the PR reads OPEN/DIRTY for minutes; a repo PATCH reads back unchanged for seconds; ask git, or retry the read with backoff, before calling a write failed

On a CLEAN PR with every check finished, `gh pr merge --auto` has exited non-zero ("merge already in
progress") while GitHub merged the PR (gateway #33 2026-10-10, agent-fabric #237 2026-10-13). For minutes
after, the PR API read OPEN, then CONFLICTING/DIRTY, while the merge commit was already on origin/main.
A tool that judges by the API calls a merged PR blocked. The fix (agent-fabric branch
for/user/arm-merged-readback, tools/fabric/github/landed.py): fetch the base and run
`merge-base --is-ancestor <head> origin/<base>`. Only a yes is acted on. A squash or rebase merge never
makes the head an ancestor, so for those the API's answer stands.

The same lag hits a settings write (2026-10-28). The owner ran `fabric-repo-policy apply
--yes`. Its immediate GET after a successful repository PATCH returned the pre-write fields,
and apply exited 1 ("still differs"). Seconds later, verify was clean. The ruleset POST read
back right. #414 (repo_policy.py READ_BACK_WAITS 1, 2, 4, 8 s) retries only when a write
landed. **How to apply:** any read-after-write against GitHub's API (merge state, repo fields)
retries with backoff, or reads a source that cannot lag (git ancestry, the write's own
response), before it reports the write as failed.

*Observed 2026-10-31 (devex-tooling)*
