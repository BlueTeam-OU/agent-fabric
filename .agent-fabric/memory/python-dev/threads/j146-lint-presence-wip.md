---
role: "python-dev"
class: threads
topic: "j146-lint-presence-wip"
description: "j146 (j337) lint presence-in-read-tree patch is written and uncommitted in a worktree; what is left to do"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ea5698a646ca375a
---

## j146 (j337) lint presence-in-read-tree patch is written and uncommitted in a worktree; what is left to do

j146 = request 01a161ac-f068-7bfd-9f9d-eed84998edca (fabric-coordinator, `develop-qzapp/user`):
`tools/fabric/lint.py` `arm_declared_findings` / `gzcoord_declared_findings` must judge presence of
arm.json / gzcoord config in the tree each is read from (operator under AGENT_FABRIC_OPERATOR).
Delivery is a patch, not a PR: tests committed on `for/user/<what>` branch, the never-list file
change left UNCOMMITTED, a REPLY carrying `git diff -- tools/fabric/lint.py` verbatim with branch and head.

State when this session ended (2026-10-22):
- worktree `~/projects/agent-fabric-j146-lint-presence`, branch
  `develop-qzapp/python-dev-01/for/user/j337-lint-presence-in-read-tree`, off origin/main e183f60d.
- uncommitted: `tools/fabric/lint.py` (helper `_present_in_read_tree`, used by both findings; None when
  the tree is the engine and non-git, so the old "absence proves nothing" case stays) and
  `tests/test_lint.py` (new `case_presence_is_judged_in_the_tree_the_file_is_read_from`, registered in main()).
  Copy of the diff: `~/agent-fabric-tmp/j146-wip.diff`.
- done: tests/test_lint.py 80/80 with the patch; the new case FAILS on original lint.py (first assertion, git operator).
- left: commit the test (`Kind: work`; the hook refused in the j145 session, a fresh session must), full
  `tests/run.sh` with CI env (env -i), then the REPLY with the diff.

**Why:** the commit hook ties a session to one job (ADR-037); j145 ended in the same session.
**How to apply:** `fabric-jobs` take j146 in the fresh session, finish the three left items above.

*Observed 2026-10-22 (python-dev)*
