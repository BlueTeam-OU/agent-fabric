---
role: "python-dev"
class: workflow
topic: "review-rounds-pin-commit-ids-run-in-worktree"
description: "fabric-review next and fabric-pr post-review traps — range must be full commit ids, run from the PR's worktree, any later commit voids head coverage"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1fe443cb87ffc742
---

## fabric-review next and fabric-pr post-review traps — range must be full commit ids, run from the PR's worktree, any later commit voids head coverage

- `fabric-review next REQUEST --report F --head <sha>` refuses a request whose
  `range` ends in `HEAD`/`origin/main..HEAD`: rewrite round 1's range as
  `<base sha>..<head sha>` (full ids) in the request file first.
- `fabric-pr post-review|gate|arm` resolve the repository from the cwd's origin:
  run them from the PR's worktree, not from `/var/tmp` or the main checkout
  (else "origin is not a github.com repository").
- Even a docstring-only fix after a posted review leaves the head uncovered
  (`gate` says "not covered"): do the re-review of the fix range and post it;
  commit any rewrap *before* dispatching so the re-review pins the final head.
- `fabric-jobs sweep` does not close a job whose artifact says "PR #N": write
  `agent-fabric #N`.

**Why:** each cost a round trip in the j45 PR (2026-10-18).
**How to apply:** build the request with pinned ids, finish all edits, then review.

*Anchors: `tools/fabric/review_rounds.py::previous ranges head`*

*Observed 2026-10-18 (python-dev)*
