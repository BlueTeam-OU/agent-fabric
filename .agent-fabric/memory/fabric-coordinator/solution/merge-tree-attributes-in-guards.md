---
role: "fabric-coordinator"
class: solution
topic: "merge-tree-attributes-in-guards"
description: "A guard that recomputes a merge (git merge-tree) in CI must not read merge attributes from the checkout it is judging"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 631e3b4622fee4ba
---

## A guard that recomputes a merge (git merge-tree) in CI must not read merge attributes from the checkout it is judging

`git merge-tree --write-tree` honours `.gitattributes` from the working tree
and from `core.attributesFile`. In CI the working tree is the branch being
judged, so a branch with `<path> merge=union` can turn a conflict into a
"clean" merge. A guard that accepts "the tree equals the clean merge of its
parents" then passes a hand-resolved conflict. The review of #341 found
this; a mutation run confirmed it.

**How to apply:** run it as
`git -c core.attributesFile=/dev/null --attr-source=<empty tree> merge-tree …`
(git 2.40 or later; exit 129 means the git is older, and is refused with its
own reason). Get the empty tree from `git hash-object -t tree --stdin </dev/null`
so it works under both hash algorithms. Pin each half with a case that fails
without it: an untracked checkout `.gitattributes`, and a `GIT_CONFIG_GLOBAL`
attributes file. `$GIT_DIR/info/attributes` and the system file are still read;
the judged branch can write neither. Related: [[arm-after-checks-not-during]].

*References: arm-after-checks-not-during*

*Anchors: `tools/fabric/guards/ban_unsigned_commits.py::--attr-source`, `tests/test_signing_rule5.py::merge=union`*

*Observed 2026-10-20 (fabric-coordinator)*
