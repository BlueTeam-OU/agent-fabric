---
role: "python-dev"
class: workflow
topic: "j190-fd-wait-race-merged-427"
description: "waiting on a /proc/<pid>/fd entry races the child's own fds; helper pattern, review-tool traps hit in #427"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4d94f3c0ceeabe15
---

## waiting on a /proc/<pid>/fd entry races the child's own fds; helper pattern, review-tool traps hit in #427

#427 (merged 2026-10-30): a test that waits for a child to hold a file open must wrap both `os.listdir(/proc/pid/fd)` and each `os.readlink` in `except OSError` (`sh -c 'exec sleep'` holds fds briefly), and assert after the bounded loop that the wait succeeded, or a timeout falls through silently.

**Why:** CI platform-smoke debian errored with FileNotFoundError on /proc/<pid>/fd/3; a "positive control" that calls a saved original function (`real = os.readlink`) cannot fail — review F1.

**How to apply:** Review-tool traps this time: `fabric-review next --pr` finds rounds by the WORKTREE's name, so run `fabric-review save` and `next` from the job worktree, not agent-fabric; a request with `range: origin/main..<sha>` needs `card_base:` (round 1's base_sha) for the re-review; `repository:` is a local path, not owner/repo. Arming under 8 work commits on the owner's word: `--basis "the owner's word (...)"`; here it merged at once. See [[post-review-needs-a-file-the-owner-can-run]].

*References: post-review-needs-a-file-the-owner-can-run*

*Anchors: `tests/test_branches_sweep.py::holds_open`*

*Observed 2026-10-30 (python-dev)*
