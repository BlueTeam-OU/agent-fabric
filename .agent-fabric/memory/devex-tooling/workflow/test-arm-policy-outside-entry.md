---
role: "devex-tooling"
class: workflow
topic: "test-arm-policy-outside-entry"
description: "Which agent-fabric tests of tools/fabric/github/ code are outside devex-tooling's authority entry (test_wait_merged.py is; test_arm_policy.py, and test_fabric_pr.py + test_pr_counts.py from 0cae803a, are in); an outside hunk goes to…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - eb7f1f98f8be9b42
---

## Which agent-fabric tests of tools/fabric/github/ code are outside devex-tooling's authority entry (test_wait_merged.py is; test_arm_policy.py, and test_fabric_pr.py + test_pr_counts.py from 0cae803a, are in); an outside hunk goes to fabric-coordinator as a patch

In agent-fabric, `policies/authority.json`'s devex-tooling entry holds all of `tools/fabric/github/` but only
the test files it names. As of 2026-10-13 `tests/test_arm_policy.py` IS in the entry (added after j112, where
its hunk went as a patch), but `tests/test_wait_merged.py` is NOT, though `wait_merged.py` is mine: the
pre-commit hook refuses a commit staging it. j114 (branch for/user/arm-merged-readback) sent its
test_wait_merged.py hunk to fabric-coordinator as a patch. Also outside (j118, 2026-10-13):
`tests/test_fabric_pr.py` and `tests/test_pr_counts.py`, though pr_counts.py and fabric_pr.py are mine; their
hunks went inline as a PATCH: section in REPLY relay seq 153958 (gzcoord-send validates such a section).
Update 2026-10-14: fabric-coordinator's 0cae803a (on develop-qzapp/user/feat/names-codex-optional, not yet on
main) adds test_pr_counts.py and test_fabric_pr.py to the entry; j122 committed test_pr_counts.py on a branch
based on it. On a branch off main they stay outside until that PR merges: check the entry on your base.

**Why:** the entry lists test files one by one; a module being mine does not make its test mine.
**How to apply:** before touching a github/ module, `jq` the entry for its test file; plan an outside test
hunk as a patch from the start and say so in the reply, or ask fabric-coordinator to add the file.

*Observed 2026-10-14 (devex-tooling)*
