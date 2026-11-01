---
role: "domain-transit"
class: workflow
topic: "inbox-watch-only-as-tracked-task"
description: "Start gzcoord-inbox --until-delivery only as a harness background task, never with & / disown inside a compound command"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e3817bb7ec64d4ce
---

## Start gzcoord-inbox --until-delivery only as a harness background task, never with & / disown inside a compound command

On 2026-10-21 I started `gzcoord-inbox --until-delivery >/dev/null 2>&1 & disown` at the
head of a compound Bash command. That watch then holds the per-login watch mark: a
proper background watch is refused ("a watch is already running"), the hooks refuse to
kill it, and any delivery it takes goes to /dev/null.

**Why:** one watch per login, and a watch is never killed; only the harness's
`run_in_background: true` call keeps its output and re-invokes the session.
**How to apply:** the watch is always its own Bash call with `run_in_background: true`.
If a stray one exists, wait it out with a tracked `while [ -d /proc/<pid> ]; do sleep 30; done (the guard refuses kill -0 on a watch pid)`
background task, then `gzcoord-inbox --history` (and `--replay <seq>`) for anything it
swallowed, then arm a normal watch.

*Anchors: `tools/fabric/gzcoord/inbox.py::--until-delivery`, `tools/fabric/gzcoord/inbox.py::--history`*

*Observed 2026-10-21 (domain-transit)*
