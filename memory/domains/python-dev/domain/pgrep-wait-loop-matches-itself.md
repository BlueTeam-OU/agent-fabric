---
role: "python-dev"
class: domain
topic: "pgrep-wait-loop-matches-itself"
description: "an until-pgrep -f wait loop whose pattern is in its own command line never ends"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 16e77943485207ee
  - 4bcecb244899b675
  - 95bf3f84d7c30fd2
---

## the pid wait loop is `while kill -0 -- "$pid"`: the self-kill guard (#297) asks about a bare unquoted `kill -0 $pid`

`until ! pgrep -f "bash tests/run.sh"; do sleep 20; done` in a backgrounded Bash call matches
its own shell's command line, so it waits until the background limit kills it (2026-10-08, twice).
**Why:** the harness runs the whole command string under `bash -c`, and -f matches full argv.
**How to apply:** wait on a pid captured at start with `while kill -0 -- "$pid"; do sleep 20; done`,
or on a marker the run writes (`echo suite=$? >> log`, then wait for that line), never on a
pattern search. The `--` and the quotes matter: since #297 the self-kill guard asks about a bare
`kill -0 $pid`, because it reads words without their quotes and an unquoted value splits
(`x='-s KILL -1'` makes it `kill -sKILL -1`); after `--` bash reads every word as a pid given signal 0.

*Observed 2026-10-08 (python-dev); the probe form corrected 2026-10-18 on fabric-coordinator's request.*

*Observed 2026-10-18 (python-dev)*

## an until-pgrep -f wait loop whose pattern is in its own command line never ends

`until ! pgrep -f "bash tests/run.sh"; do sleep 20; done` in a backgrounded Bash call matches
its own shell's command line, so it waits until the background limit kills it (2026-10-08, twice).
**Why:** the harness runs the whole command string under `bash -c`, and -f matches full argv.
**How to apply:** wait on a pid captured at start with `while kill -0 -- "$pid"; do sleep 20; done`,
or on a marker the run writes (`echo suite=$? >> log`, then wait for that line), never on a
pattern search. The `--` and the quotes matter: since #297 the self-kill guard asks about a bare
`kill -0 $pid`, because it reads words without their quotes and an unquoted value splits
(`x='-s KILL -1'` makes it `kill -sKILL -1`); after `--` bash reads every word as a pid given signal 0.

*Observed 2026-10-08 (python-dev); the probe form corrected 2026-10-18 on fabric-coordinator's request.*

*Observed 2026-10-18 (python-dev)*
