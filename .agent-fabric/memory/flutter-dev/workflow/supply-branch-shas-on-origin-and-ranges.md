---
role: "flutter-dev"
class: workflow
topic: "supply-branch-shas-on-origin-and-ranges"
description: "In a supply hand-off, a sha is named only after `git ls-remote` shows it on origin, and the caller folds the NAMED sha after reading base..sha for commits that are not the supply."
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 131b8ceca7d1fc68
---

## In a supply hand-off, a sha is named only after `git ls-remote` shows it on origin, and the caller folds the NAMED sha after reading base..sha for commits that are not the supply.

Both directions of a supply hand-off failed in one week:

- **As caller**, I sent a REQUEST whose DELIVER-TO branch and base sha
  existed only in my clone; the supplier found "not a valid object
  name" and could not push. Days later a supplier's commit had to add
  an en-US line my REQUEST assumed was there — my commit was still
  local.
- **As receiver**, a supplier committed an unrelated task onto the
  branch it had handed me (two commits, fifteen foreign keys, above the
  tip). Another time the branch I was told to fold had been rewritten:
  the expected shas were gone, replaced by commits carrying strings from
  another surface. Suppliers who did it well said in the same minute
  that the tip had moved, and why.

**How to apply:**
- Before sending `DELIVER-TO: <branch> <base-sha>`, push and confirm
  with `git ls-remote --heads origin <branch>` that the sha is the
  head — not from the push output alone. Every line the supplier is told
  exists must be on that remote head.
- Before folding a supply, `git log --oneline <base>..<named-sha>` and
  read every commit; fold the named sha (`git merge --no-ff`), never a
  tip that moved since. If the range carries more than the supply,
  say so to the asker and in the PR body's range line.
- As supplier, announce any move of a handed-off tip at once.
Related: [[session-batch-arming-class-and-supply]].

*References: session-batch-arming-class-and-supply*

*Anchors: `.claude/skills/owed-supply/SKILL.md::DELIVER-TO`*

*Observed 2026-10-18 (flutter-dev)*
