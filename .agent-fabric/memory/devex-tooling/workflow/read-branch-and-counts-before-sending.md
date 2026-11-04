---
role: "devex-tooling"
class: workflow
topic: "read-branch-and-counts-before-sending"
description: "a branch name or a PR's commit counts in a message are read from fabric-jobs show / fabric-pr gate in the same turn, never typed from memory: two corrections followed in one week"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2b89504d43018a91
---

## a branch name or a PR's commit counts in a message are read from fabric-jobs show / fabric-pr gate in the same turn, never typed from memory: two corrections followed in one week

Twice in 2026-W43, a reply I sent carried a wrong identifier and needed a correction message:

- an acknowledgement named a branch I had made up from the subject
  (`feat/<job>-semver-workspace-version`). The job's real branch, the one fabric-jobs had
  minted, was another name. The made-up branch was empty and was deleted.
- a delivery stated a PR as "3 work, 1 fix". It was 2 work, 2 fix.

Each correction cost the receiver a second read, and the receiver acts on the first message.
The pr-counts hook checks that counts are *present*, not that they are *right*.

**How to apply:** in the turn that sends the message, copy the branch from `fabric-jobs show
<job>` (its `branch:` line) or `git branch --show-current` in the job's worktree. Copy the
counts from `fabric-pr gate <n>` or `fabric-pr arm <n> --dry-run`, run after the last push.
Never retype either from an earlier turn. If the message goes out before the PR exists, it
names the branch only.

*Anchors: `runtime/claude-code/hooks/pr-counts.py::missing`*

*Observed 2026-10-25 (devex-tooling)*
