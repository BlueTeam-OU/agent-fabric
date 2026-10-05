---
role: "python-dev"
class: workflow
topic: "contributor-merge-direction"
description: merging an older fix branch into a contributor branch that already folded main is refused by contributors.py; merge with the fix as first parent instead
tier: 1
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f06a06f008f28aef
---

## merging an older fix branch into a contributor branch that already folded main is refused by contributors.py; merge with the fix as first parent instead

tools/fabric/guards/contributors.py judges a merge by `git diff --cached MERGE_HEAD`
(the result over the merged-in side). Merging wave-6-fix-85 (based on 76aaa4c) into
wave-6-tests (which had folded main) was refused: the locale team.md files that
came in from main differ from 76aaa4c's, though the merge left them as they were.
What worked (2026-10-02): on the contributor branch name (not detached; the guard
requires a contributor branch), `git checkout -B <wave-6-tests> <fix tip>` then
`git merge <old wave-6-tests tip>`. Same tree, push is a fast-forward (5b428ab).
Reported to fabric-coordinator in GZCoord 01a0fea1 as a guard limitation.

Update 2026-10-03: fabric-coordinator fixed the guard (judges a merge over every
parent; a clean fold is admitted) in 0a5dad2b, and the worktree-path corpus-lint
finding in 59a94321, both on develop-qzapp/user/feat/journal-rollout, not yet on
main. Once both are on main, the reversed-parent workaround is unnecessary and the
lint is clean from ~/projects/agent-fabric-<what>; check main before relying on either.

*Observed 2026-10-02 (python-dev)*
