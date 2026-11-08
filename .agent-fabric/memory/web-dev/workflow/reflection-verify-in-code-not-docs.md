---
role: "web-dev"
class: workflow
topic: "reflection-verify-in-code-not-docs"
description: "In a reflection pass, a broadcast's instruction may already be enforced in code — grep origin/main's code, not only the ADRs/docs, before admitting it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "web-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - abc24b7f42339413
---

## In a reflection pass, a broadcast's instruction may already be enforced in code — grep origin/main's code, not only the ADRs/docs, before admitting it

Reflection pass 2026-W42 (through row 214, 2026-10-18): the owner's disk broadcast
(01a14a95, "point build scratch at your home, not /var/tmp") looked unrecorded in
the ADRs and docs, but the launcher already sets TMPDIR to ~/agent-fabric-tmp
(tools/fabric/launcher/session.py); this session's /var/tmp TMPDIR only meant it
was launched before that change. Admitted nothing that pass.

**Why:** a lesson the code already enforces fails RUBRIC tests 1 and 6.
**How to apply:** before writing a reflection lesson, `git grep` origin/main's code
for its literal, and compare your own environment against what the current launcher
would set.

Pass 2026-W43 (rows 234–240, 2026-10-25): it held again. The sweep-removes-a-job's-worktree
correction (01a16e7d) was already fixed in tools/fabric/branches.py ("named by job jN").

Pass 2026-W44 (through row 246, 2026-10-31): third time. The /clear sweep caveat
(01a17c38, "fix queued with python-dev-01") had landed: tools/fabric/branches.py
checks /proc for a live process using a session's scratch, tested in
tests/test_branches_sweep.py. The other five messages were events or already in
skills/charter (hygiene, disk, hold, cpu slots). Admitted nothing.

*Observed 2026-10-31 (web-dev)*
