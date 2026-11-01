---
role: "python-dev"
class: solution
topic: "named-anchor-j307-merged-340"
description: "Named anchors <project>:<path>::<symbol> (merged #340): where each part lives, and the two CI traps the work hit"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cf6b002c661e8d59
---

## Named anchors <project>:<path>::<symbol> (merged #340): where each part lives, and the two CI traps the work hit

Named anchors are read by `anchors.split`; harvest and assembler intake call `registry_problem` (an empty registry id list is said as "could not be read", not as an unknown name); `memory_check.named_trees` picks the checkout (own project: the tree; origin working_copy, else the id; absent: unchecked); `memory_hint` keys diffs by (tree, path).

**Why:** two traps cost a round each. A test that copied the live `projects/registry.json` into a scratch fabric failed CI's `test_tests_read_fixtures` (write a fixture registry); and my local lint run read the session root, not the worktree, so it missed a managed-project name in a generic file (run lint with `env -u AGENT_FABRIC_ROOT`, see [[lint-in-a-worktree-reads-the-session-root]]).

**How to apply:** a test that needs a registry writes one into its scratch fabric; a placeholder in a generic file is `other-project`, never a registry id. Memory-index still keys a named anchor as `path:<project>:<path>` (no link to the unnamed form).

*References: lint-in-a-worktree-reads-the-session-root*

*Anchors: `tools/fabric/anchors.py::registry_problem`, `tools/fabric/memory_check.py::named_trees`*

*Observed 2026-10-20 (python-dev)*
