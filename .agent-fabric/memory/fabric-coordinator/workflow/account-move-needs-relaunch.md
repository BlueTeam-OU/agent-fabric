---
role: "fabric-coordinator"
class: workflow
topic: "account-move-needs-relaunch"
description: "fabric-accounts assign --no-restart only changes the assignment: a running session keeps its old token until it relaunches; check the claude process start time, not fabric-ctl status"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4e5c84a8bdd3fee1
---

## fabric-accounts assign --no-restart only changes the assignment: a running session keeps its old token until it relaunches; check the claude process start time, not fabric-ctl status

2026-10-15: the owner noticed architect-cto-01 was not running on andrea-benetton-blueteam-ge a day after I moved the 14 gzapp logins there with `--no-restart`. `fabric-ctl all status` showed every one on the new setup-token (183a68e97389), but that column is the assigned sign-in; 11 sessions had started on 13 Oct before the move and still ran on the old token. Re-running `fabric-accounts assign <logins> <account>` without `--no-restart` relaunched them (it skips a login whose session is already on the account).

**Why:** the assignment and the live session diverge silently; the usage then lands on the wrong account.

**How to apply:** after any `assign --no-restart`, check each login's claude process start time (`ps -u <login> -o lstart=,args=`) against the move; relaunch the idle ones the same day, or say which are left on the old account. Related: [[subscription-pool-settled]], [[accounts-moved-2026-10-10]].

*References: accounts-moved-2026-10-10, subscription-pool-settled*

*Observed 2026-10-15 (fabric-coordinator)*
