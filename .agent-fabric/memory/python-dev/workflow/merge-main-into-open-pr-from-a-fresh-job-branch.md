---
role: "python-dev"
class: workflow
topic: "merge-main-into-open-pr-from-a-fresh-job-branch"
description: "j119 #579: the PR branch is checked out in the old job's worktree and the hook refuses commits there; reset the new job's own branch to the PR head, merge, push HEAD:<pr branch>"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8bd21e96ffd0ff65
---

## j119 #579: the PR branch is checked out in the old job's worktree and the hook refuses commits there; reset the new job's own branch to the PR head, merge, push HEAD:<pr branch>

A follow-up job (merge origin/main, re-review, re-arm) starts in a fresh worktree on its own branch, while the PR branch stays checked out in the earlier job's worktree. The PreToolUse hook refuses `git merge` there ("works one job's working copy", ADR-037 rule 3).

**How to apply:** in the new job's worktree `git reset --hard <PR head sha>`, `git merge origin/main`, then `git push origin HEAD:<PR branch>`. Write a `mode: review` request with `range: <origin/main sha>..<head sha>`, `evidence: pinned`, `pr: N`. Dispatch the brief verbatim and extract the report from the subagent's output JSONL by script. Post it with the bare `fabric-pr post-review N < file` (no cd, no pipe, no `2>&1`). The push disarms the PR: `arm --basis` again, which works while checks are still pending (auto-merge waits). Close with `fabric-jobs done jN <owner/repo#N>` once merged; `deliver` refuses a merged PR. Counts at #579: 1 work, 1 fix, 2 merge; minimum 1. [[rereview-after-main-merge-reads-nothing-covers-no-head]] [[ci-rerun-replays-the-stale-merge-ref]]

*References: ci-rerun-replays-the-stale-merge-ref, rereview-after-main-merge-reads-nothing-covers-no-head*

*Anchors: `bin/fabric-review::next`*

*Observed 2026-11-13 (python-dev)*
