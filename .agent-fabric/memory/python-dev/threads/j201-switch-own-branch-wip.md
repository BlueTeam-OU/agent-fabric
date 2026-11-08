---
role: "python-dev"
class: threads
topic: "j201-switch-own-branch-wip"
description: "j201 (switch never re-points a job with its own branch): PR #471 open, reviewed twice, REPLY sent; only CI and arming (owner's word) remain"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 66797d4a58b3722b
---

## j201 (switch never re-points a job with its own branch): PR #471 open, reviewed twice, REPLY sent; only CI and arming (owner's word) remain

j201 = REQUEST 01a1a3ec-45e6-72a3-bb92-ca6b27539491 (develop-qzapp/user). PR BlueTeam-OU/agent-fabric#471 (1 work, 1 fix at 50fd10f2), branch develop-qzapp/python-dev-01/feat/j201-fabric-jobs-switch-never-re-point. REPLY with the number sent (seq 804681).

**Done 2026-11-04:** change + 5 mutations killed + full suite green + review round 1 (F1 P3, fixed: `_landed` asked before the gone check) + re-review none; both posted.

**Left:** CI checks pending at last gate read; arming is below the 8-work minimum, so it needs the owner's word (`fabric-pr arm --dry-run 471`, basis required). Then job done, tell fabric-coordinator it merged. Open for the owner: a landed recorded branch leaves only done/drop.

**Traps met:** a stray `cat > file` in a chained Bash call waits on stdin forever (TaskStop it); `python3 -I tests/x.py` drops the tests dir from sys.path; `fabric-review save` takes no --repo with a slash; `next` needs sha-pinned range and `--head`.

*Observed 2026-11-04 (python-dev)*
