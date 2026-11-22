---
role: "python-dev"
class: domain
topic: "lock-file-separate-from-replaced-journal"
description: flock on a file that is atomically replaced is lost to a contender that opened the old path; and a guard around a decision needs a test that makes the decision raise
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0023c467cd0141cf
---

## flock on a file that is atomically replaced is lost to a contender that opened the old path; and a guard around a decision needs a test that makes the decision raise

A lock held on the inode of a file that is later replaced (os.replace) excludes nobody: a second process that opened the old path before the replace and locks after the holder closes its old fd locks the unlinked inode and appends records no restart reads. Lock a stable file that is never replaced, take it before opening the data file (carrier `deliveries.lock`, agent-fabric#476, `tools/fabric/gzcoord/carrier/record.py`). Test it by pausing the contender between open and flock (patch the module's `fcntl` per thread), compacting, accepting, restarting.

A try/except added around a decision (agentd `accept()`) is only evidenced by a test that makes the decision raise: the malformed input that motivated it stops raising once the formatter is fixed, so the first test passed with the guard deleted. A driver script that wraps the real function and raises for one id, run as the daemon's subprocess, fails when the guard is removed (reviewer round 1, F2).

**Why:** both were caught only by an external review and a blind review respectively; green tests hid them.
**How to apply:** for any lock, ask which inode it names after a replace; for any new catch, mutate it away and watch a test fail.

*Observed 2026-11-04 (python-dev)*
