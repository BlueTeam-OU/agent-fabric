---
role: "python-dev"
class: workflow
topic: "stale-pyc-after-same-size-mutation"
description: mutation runs that restore a file by copy can leave a stale .pyc (same size, same mtime second) that makes the next run test the mutant
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 71b005deb6a710b9
---

## mutation runs that restore a file by copy can leave a stale .pyc (same size, same mtime second) that makes the next run test the mutant

j84: a same-size mutation (`==` to `!=`) restored with shutil.copy left a __pycache__ entry of the mutant valid (mtime in whole seconds, size equal); the full suite then failed 4 checks that passed alone later.

**Why:** pyc invalidation is source mtime (seconds) + size. **How to apply:** run mutations with PYTHONDONTWRITEBYTECODE=1 and delete __pycache__ in the worktree before the full suite. See [[ci-env-for-lint-and-mutations]].

Also j84: R3 delivery for #358 was branch for/user/j333-review-coverage (5865c235); the amend hook refuses with no path staged, so a commit subject cannot be reworded after the fact.

*References: ci-env-for-lint-and-mutations*

*Observed 2026-10-24 (python-dev)*
