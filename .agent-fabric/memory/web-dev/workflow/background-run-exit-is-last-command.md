---
role: "web-dev"
class: workflow
topic: "background-run-exit-is-last-command"
description: "Running a PR watcher or any verdict-by-exit-code script in the harness's background mode: why the reported exit can lie"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 12fe01cad636a464
---

## Running a PR watcher or any verdict-by-exit-code script in the harness's background mode: why the reported exit can lie

When a command runs in the harness's background mode, the exit code it
reports belongs to the whole command line's LAST command. That is not the
script you care about. Three shapes lose or fake the verdict of a watcher
whose exit code is its answer (e.g. a wait-merged script, where 0 means
MERGED):

- `watcher & sleep 1; echo started` reports 0 within a minute: that is the
  wrapper's exit. The watcher is orphaned, so nothing is watching, and the 0
  reads as "merged". Measured: the log said "blocked, checks still
  pending" and `gh pr view` said OPEN.
- `watcher; echo "EXIT=$?"` reports the echo's 0. The real exit was 6
  (STALLED).
- `( watcher & )` detaches, so no notification ever arrives.

What works: the script is the whole command, backgrounded by the harness,
with nothing appended. In each case, the control run in that shape returned
the true verdict.

**Why:** a session that relays "it merged" from that exit code reports an
assumption as a fact.

**How to apply:** a script whose exit code is the answer runs bare in the
background runner. A `&` that a doc shows is meant for a shell that stays
open; drop it under the runner. Read the output file before you trust the
code.

Sources (GZCoord): 01a0b626-e2b8-7861-a848-82c2b6e2138e (this login, gzapp
#870), 01a0b626-f27e-7189-907a-3fe619237012 (another agent, gzapp #880).

*Anchors: `tools/fabric/github/wait_merged.py::MERGED — safe to return to main`*

*Observed 2026-10-18 (web-dev)*
