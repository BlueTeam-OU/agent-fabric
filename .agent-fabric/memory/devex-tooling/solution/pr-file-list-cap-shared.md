---
role: "devex-tooling"
class: solution
topic: "pr-file-list-cap-shared"
description: "GitHub's PR file list stops at 3000 without error; every reader of it in tools/fabric/github/ refuses at common.PR_FILE_LIST_CAP (arm since j282, post_review before)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f21e1ef3e89bfe1
---

## GitHub's PR file list stops at 3000 without error; every reader of it in tools/fabric/github/ refuses at common.PR_FILE_LIST_CAP (arm since j282, post_review before)

GitHub's `pulls/N/files` lists at most 3000 files, paginated or not, with no error. arm read it as whole for
the boundary, class and no-CI checks, so 3000 docs paths armed docs-only (external review F08, j282, commit
208a7a91 on develop-qzapp/devex-tooling/for/user/j282-arm-file-list-cap). The cap is now one constant,
`common.PR_FILE_LIST_CAP`; arm answers exit 2 at it, post_review's locale_only returns False. The commit list's
250 cap is still per module (arm PR_COMMITS_CAP, pr_counts REST_COMMIT_CAP, post_review, review_checkpoint).

**Why:** a capped list is a part of the change; any gate judged on it judges only that part.
**How to apply:** a new reader of a PR's files or commits imports the cap and refuses at it; test with a list
of exactly the cap, plus the cap minus one as the control. See [[gate-relaxing-marker-trusted-structured-head]].

*References: gate-relaxing-marker-trusted-structured-head*

*Anchors: `tools/fabric/github/common.py::PR_FILE_LIST_CAP`, `tools/fabric/github/arm.py::PR_FILE_LIST_CAP`*

*Observed 2026-11-04 (devex-tooling)*
