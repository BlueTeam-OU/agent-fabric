---
role: "devex-tooling"
class: workflow
topic: "outside-entry-supply-as-staged-diff"
description: "a supply outside my authority entry cannot be committed, so no format-patch; stage it in a worktree, review INDEX..WORKTREE, send git diff --binary + message"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 35ac458b250b0f40
---

## a supply outside my authority entry cannot be committed, so no format-patch; stage it in a worktree, review INDEX..WORKTREE, send git diff --binary + message

In agent-fabric the commit-msg/pre-commit fence refuses any commit touching paths outside devex-tooling's entry in policies/authority.json (runtime/claude-code/, tests/run.sh, tests/test_user_settings_*), even on a for/user/ branch (j124, 2026-10-14). So a route that promises "a git format-patch" cannot be kept: there is no commit to format.

**Why:** the fence keys on paths, not branch; bypassing it (--no-verify, a hookless clone, stash-create) would be evading the control plane's lane rule.

**How to apply:** build in a worktree off origin/main, `git add` the supply (the index is the reviewed state), and brief the code-review class with repository = the worktree and range `origin/main..INDEX` (`git -C <wt> diff --cached origin/main`); it can read a worktree, unlike the scratchpad ([[review-class-cannot-read-scratchpad-diff]]). Fixes stay unstaged, so a re-review range is `INDEX..WORKTREE` (`git diff`); `fabric-review brief` needs previous_findings as a file path for a re-review. Deliver `git diff --binary` plus the commit message for fabric-coordinator to apply and commit, and say in the hand-off that it is a diff, not a format-patch.

*References: review-class-cannot-read-scratchpad-diff*

*Observed 2026-10-14 (devex-tooling)*
