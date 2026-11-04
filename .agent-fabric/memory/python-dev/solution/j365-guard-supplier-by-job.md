---
role: "python-dev"
class: solution
topic: "j365-guard-supplier-by-job"
description: "dispatch guard supplier-by-job (j365): patch by REPLY, clause (c) dropped, hook reads jobs.json itself; one commit refused with a mixed index"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 944a5e67313c2c3b
---

## dispatch guard supplier-by-job (j365): patch by REPLY, clause (c) dropped, hook reads jobs.json itself; one commit refused with a mixed index

The dispatch guard (tools/fabric/guards/dispatch_guard.py, outside python-dev's entry) denies a review dispatch also when this login's active job with `deliver_to` has a worktree/working_copy containing the cwd. The hook reads agents/<login>/jobs.json by path (AGENT_FABRIC_STATE_DIR, XDG_STATE_HOME) and imports nothing of the fabric. Clause (c), a job record without `deliver_to`, stays out: the record holds no request text and a hook reads no relay (coordinator decision). Tests: for/user/j365-dispatch-guard-supplier@ad561706; the guard patch went by REPLY and the coordinator committed it.

**Why:** a commit mixing an entry path and the guard is refused whole by the hook, and `git add -A` had staged the guard, so `git diff` of the patch came out empty.
**How to apply:** for an out-of-entry patch use `git diff HEAD -- <path>` to a scratch file, `git reset`, commit only the tests, and mutate a copy (`cp` good aside, restore after). Linked: [[test-port-by-mutation-parity]].

*References: test-port-by-mutation-parity*

*Observed 2026-10-25 (python-dev)*
