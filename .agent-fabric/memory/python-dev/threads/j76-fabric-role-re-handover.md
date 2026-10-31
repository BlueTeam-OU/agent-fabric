---
role: "python-dev"
class: threads
topic: "j76-fabric-role-re-handover"
description: j76 (REQUEST 01a16199, j303) handover to the fresh session — test patch saved, fix is one line, delivery is a diff by REPLY
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 260684468abef154
---

## j76 (REQUEST 01a16199, j303) handover to the fresh session — test patch saved, fix is one line, delivery is a diff by REPLY

j76: compile `FABRIC_ROLE_RE` (tools/fabric/guards/commit_hooks.py:79) as `re.I | re.ASCII`. Delivery (fabric-coordinator's rule, 2026-10-22): the test is committed on a `develop-qzapp/python-dev-02/for/user/<what>` branch; the never-list file change stays UNCOMMITTED; the REPLY carries `git diff -- tools/fabric/guards/commit_hooks.py` verbatim with the branch and its head, and the `tests/run.sh` result (CI environment). No PR.

The test is written and verified: `~/agent-fabric-tmp/j76/test-commit_hooks.patch` (apply to tests/test_commit_hooks.py on origin/main; adds `import subprocess` and `Direct.test_the_role_stamp_matches_what_grep_i_matches_for_every_code_point`, ~16 s). Run on the re.I-only pattern it FAILS with exactly one disagreement, `'Fabrİc-Role: x'` (U+0130 in the place of the i); with `re.I | re.ASCII` it must pass. Show the failing run once, then the fix. A first draft missed the `i` position and passed vacuously; grep needs bytes in and out (text mode turns \r into a line end).

An ack REPLY (seq 435317) is sent; the final REPLY is owed. The old worktree ~/projects/agent-fabric-j76 holds the same test uncommitted; the hook refuses commits from a session that has worked a finished job, so commit in the fresh session.

*Observed 2026-10-22 (python-dev)*
