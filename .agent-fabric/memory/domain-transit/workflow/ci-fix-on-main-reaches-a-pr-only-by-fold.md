---
role: "domain-transit"
class: workflow
topic: "ci-fix-on-main-reaches-a-pr-only-by-fold"
description: "A PR that is red from a test or runner breakage already fixed on main stays red until origin/main is folded in; a re-run does not help, and the fold disarms"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e52c9e1a039f7abc
---

## A PR that is red from a test or runner breakage already fixed on main stays red until origin/main is folded in; a re-run does not help, and the fold disarms

A PR's CI runs the test files from the PR's own branch. When a check is red because of
something outside the diff (a runner image change, a date-dependent test) and the fix has
landed on main, the PR stays red. Re-running the old job is not enough. In gzapp this
happened twice on 2026-10-25, reported by two different roles: ban-checks after the
ubuntu-latest runner image moved, and the merge queue's status_web time-zone test.

**Why:** the fix is in main's copy of the test, which the PR's branch does not contain.
**How to apply:** when my PR fails a check its diff cannot explain, first look for a fix
on main or a broadcast about it. Then `git merge --no-ff origin/main` into the branch
(never a rebase) and push. Pushing the fold disarms an armed PR, so re-arm it after its
counts and review gate allow (see the pull-requests skill). If the fix is still only an
open PR, wait for it to land rather than queueing: the merge queue will evict my PR until then.

*Anchors: `policies/pull-requests/SKILL.md::Supplying and folding`*

*Observed 2026-10-25 (domain-transit)*
