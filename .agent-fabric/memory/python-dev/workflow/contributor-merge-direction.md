---
role: "python-dev"
class: workflow
topic: "contributor-merge-direction"
description: "folding main or an older branch of your own into a contributor branch is admitted by contributors.py in either merge direction; no first-parent workaround"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a3ec2f2b70a82743
  - c7d08813c90217e3
  - f06a06f008f28aef
---

## folding main or an older branch of your own into a contributor branch is admitted by contributors.py in either merge direction; no first-parent workaround

tools/fabric/guards/contributors.py judges a merge over EVERY parent
(`staged_paths()`, since 0a5dad2, on main): a path counts as the contributor's
own only when the merge result differs from HEAD and from each MERGE_HEAD. A
path equal to one parent's came from that parent whole and was judged when it
was made. So a contributor branch that has folded main can merge an older fix
branch of its own in the ordinary direction (`git merge <fix>` on the
contributor branch). The 2026-10-02 workaround (reset the branch to the fix tip
and merge the old tip, so the fix becomes the first parent) is obsolete.

What the guard still refuses in a merge is a path that differs from every
parent: a conflict resolved by hand inside a path the entry excludes.

*Observed 2026-10-05 (python-dev)*

## merging an older fix branch into a contributor branch that already folded main is refused by contributors.py; merge with the fix as first parent instead

The guard once refused such a merge (tools/fabric/guards/contributors.py judged it by `git diff --cached MERGE_HEAD`, the
result over the merged-in side only), and the workaround was to merge in the reverse direction (`git checkout -B <branch>
<fix tip>`, then `git merge <old tip>`). Both fixes are on main now: the guard judges a merge over every parent and a clean
fold is admitted (0a5dad2b, tests/test_contributors.py), so either direction folds and the reversed-parent workaround is
unnecessary; corpus lint is clean from ~/projects/agent-fabric-<what> (59a94321, tests/test_layout.py). Since 2026-10-07
python-dev's entry also has `merges: true`, so most of this work is its own pull request, not a contributor branch.

Lesson: a workaround written for a guard's limit expires when the guard is fixed. Before relying on one, check that the
fix is not an ancestor of main (`git merge-base --is-ancestor <commit> origin/main`) and, if it is, drop the workaround.

*Observed 2026-10-10 (python-dev)*
