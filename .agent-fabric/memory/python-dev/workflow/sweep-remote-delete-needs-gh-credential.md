---
role: "python-dev"
class: workflow
topic: "sweep-remote-delete-needs-gh-credential"
description: "fabric-branches --sweep deletes origin branches through git https and fails without a helper; a worktree pins its branch; verify \"kept\" branches by git cherry before asking"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2277d3853f3c0483
---

## fabric-branches --sweep deletes origin branches through git https and fails without a helper; a worktree pins its branch; verify "kept" branches by git cherry before asking

`fabric-branches --sweep` reports remote deletes as "KEPT ... could not read Username" on this account. Re-run with the helper inline:
`GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=credential.helper GIT_CONFIG_VALUE_0='!gh auth git-credential' fabric-branches --sweep` (see [[push-through-gh-credential]]).

Branches it keeps "with commits off main" are mostly landed under other shas: run `git cherry origin/main <branch>` (`-` = on main by patch), match subjects with `git log origin/main -F --grep`, and read `gh pr list --head <branch> --state all`. A branch used by a sibling worktree refuses `branch -D`: `git worktree remove` it first (check `status --porcelain` is empty).
A `for/` branch whose tip was never pushed is not on origin; the coordinator cannot diff it, so a line-by-line "added lines absent from main" count is only a rough signal when main has since rewritten the code.

**Why:** j226 (2026-11-11): five kept branches, four resolved by cherry/PR, one (holder-addenda) only by name match plus the coordinator's word.
**How to apply:** before asking about kept branches, run the three checks above and bring the one that stays unclear.

*References: push-through-gh-credential*

*Anchors: `tools/fabric/branches.py::--sweep`*

*Observed 2026-11-11 (python-dev)*
