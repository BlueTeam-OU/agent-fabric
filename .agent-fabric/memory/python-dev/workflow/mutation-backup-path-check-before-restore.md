---
role: "python-dev"
class: workflow
topic: "mutation-backup-path-check-before-restore"
description: "A mutation run's backup cp into a shared /var/tmp path failed silently and the \"restore\" copied a stranger's file over the source"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c6bb55a3bbef00ae
---

## A mutation run's backup cp into a shared /var/tmp path failed silently and the "restore" copied a stranger's file over the source

In j35 a mutation loop did `cp src /var/tmp/w.bak; sed -i …; cp /var/tmp/w.bak src`. The first cp failed (a file of another login owned the name, permission denied), the restore then copied that other file over worker.py (1100-line diff).

**Why:** `;` chains ran on after the failed backup, and a shared /var/tmp name is not mine.
**How to apply:** back up into the session scratchpad, chain with `&&`, and `git diff --stat` the file after every restore. Also: a test that shells out to `gh` needs a fake `gh` first on PATH, or the suite asks GitHub ([[mutation-run-read-rc-not-fail-count]]).

*References: mutation-run-read-rc-not-fail-count*

*Observed 2026-10-16 (python-dev)*
