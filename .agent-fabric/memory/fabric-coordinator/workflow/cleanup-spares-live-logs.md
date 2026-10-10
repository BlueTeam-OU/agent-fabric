---
role: "fabric-coordinator"
class: workflow
topic: "cleanup-spares-live-logs"
description: "Before deleting logs or scratch in $TMPDIR during a clean-up, check no background task of this session still writes them"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9cc41d19d3b01b02
---

## Before deleting logs or scratch in $TMPDIR during a clean-up, check no background task of this session still writes them

A clean-up (the owner's "clean up after every test run", 2026-10-08) ran
`rm $TMPDIR/*.log` while a background `tests/run.sh` still wrote its log
there: the run lost its record and ended at the 1 h limit unread.

**Why:** a glob over the session's temp dir catches the files of runs still
in flight; the run's evidence is gone and nothing says so.

**How to apply:** before removing anything under $TMPDIR or the scratchpad,
list this session's background tasks (task notifications not yet arrived)
and the files they write; delete only files no live task names. Another
login's /tmp/agent-fabric-tests.* is theirs: leave it. See
[[suite-scratch-leak]].

*References: suite-scratch-leak*

*Observed 2026-10-08 (fabric-coordinator)*
