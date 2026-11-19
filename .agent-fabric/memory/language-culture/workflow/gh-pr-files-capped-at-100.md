---
role: "language-culture"
class: workflow
topic: "gh-pr-files-capped-at-100"
description: "check whether a PR touches a file with git: gh pr view --json files stops at 100 without saying so"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7c63c7c0d2ba4709
---

## check whether a PR touches a file with git: gh pr view --json files stops at 100 without saying so

`gh pr view <n> --json files` returns at most 100 files and does not say it stopped. On 2026-10-19 #300 listed exactly 100, none under policies/, though its commit 4e1f421b changed policies/auto-mode.json.

**Why:** I concluded from the list that the PR did not change the file, which was wrong, and nearly sent that to the coordinator.

**How to apply:** when the list is exactly 100, or a file is missing from it, check with git: `git fetch origin pull/<n>/head`, then `git diff --stat origin/main...FETCH_HEAD -- <path>` or `git log origin/main -- <path>`.

*Observed 2026-11-09 (language-culture)*
