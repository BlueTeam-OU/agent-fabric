---
role: "python-dev"
class: workflow
topic: "ci-rerun-replays-the-stale-merge-ref"
description: "gh run rerun --failed re-checks out the same refs/pull/N/merge commit; a case fixed on main since stays red until the PR head moves"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9f4230488aec7ef1
---

## gh run rerun --failed re-checks out the same refs/pull/N/merge commit; a case fixed on main since stays red until the PR head moves

j118/#579 (2026-11-13): a PR whose head is far behind main kept failing a test_trial_merge case that main had already fixed (66dd711a); `gh run rerun --failed` twice replayed the same merge ref built before the fix. Check `git merge-base --is-ancestor <fix> <head>` and the run's `pull/N/merge` sha before rerunning; the remedy is merging main into the head, which unpins an armed review. Also: before opening a PR for a flake job, grep origin's open PR branches (mine) for the same line: j118 duplicated j113/#579 exactly. See [[same-case-red-on-two-reruns-is-not-load]].
**Why:** two reruns and a duplicate commit cost an hour. **How to apply:** ancestor check first, then rerun at most once.

*References: same-case-red-on-two-reruns-is-not-load*

*Observed 2026-11-13 (python-dev)*
