---
role: "python-dev"
class: workflow
topic: "j146-presence-patch-delivered"
description: "j146 (j337) lint presence-in-read-tree delivered; what the delivery taught about for/ patches, pushes and the job guard"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2a5c86cd8de01a02
---

## j146 (j337) lint presence-in-read-tree delivered; what the delivery taught about for/ patches, pushes and the job guard

j146 = request 01a161ac (fabric-coordinator): `_present_in_read_tree` in `tools/fabric/lint.py`, used by
`arm_declared_findings` and `gzcoord_declared_findings`; test `case_presence_is_judged_in_the_tree_the_file_is_read_from`
in `tests/test_lint.py`. Coordinator applied the lint.py diff as 71a83cfe; my test commit is aab17f26 on
`develop-qzapp/python-dev-01/for/user/j337-lint-presence-in-read-tree`. Follow-up is j147 (#354 round 1).

- A `for/` delivery is not delivered until the branch is PUSHED: the coordinator cannot fold a local head, and "commit" in a
  request still means push. `git ls-remote` before the REPLY.
- The commit/push hook ties the session to the one active job's worktree. `fabric-jobs deliver` moves the job out of active
  and then blocks a push; `fabric-jobs start <id>` re-activates it. Push before `deliver`.
- A second worktree for the same job is a different working copy to the hook: move the patch into the job's own worktree
  (git apply) and rename the branch there.
- A full `tests/run.sh` can wait on another agent's lease, then pass the 30-min default background limit and be killed:
  start it with `timeout: 7200000`. Watchers that grep the log for "passed" fire on the static stage; wait for
  "all suites passed" / `exit=`.
- `fabric-jobs switch` also wants the delivered change committed or discarded, every REPLY-EXPECTED answered, and a memory
  change.

**Why:** each cost a round trip this job.
**How to apply:** for a never-list patch: tests commit in the job worktree, push, REPLY with the diff, then deliver.

*Anchors: `tools/fabric/lint.py::_present_in_read_tree`, `tests/test_lint.py::case_presence_is_judged_in_the_tree_the_file_is_read_from`*

*Observed 2026-10-22 (python-dev)*
