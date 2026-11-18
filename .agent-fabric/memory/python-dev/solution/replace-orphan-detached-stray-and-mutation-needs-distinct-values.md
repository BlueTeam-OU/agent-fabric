---
role: "python-dev"
class: solution
topic: "replace-orphan-detached-stray-and-mutation-needs-distinct-values"
description: "gzcoord-inbox --replace orphan rule (j123 #607): detached/ended/two-line+reparented; a hand-armed `( cmd & )` watch is recorded detached; review traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b2e8dea3248e841d
---

## gzcoord-inbox --replace orphan rule (j123 #607): detached/ended/two-line+reparented; a hand-armed `( cmd & )` watch is recorded detached; review traps

`--replace` (watchlock.replaceable_of, #607, 2026-11-14) ends a same-uid inbox watch the lock file names when its session is
ended, its kind is `detached`, or a two-line file's holder is `reparented`. A live other session, another uid, an unnamed holder,
a start-less session and unknown session lines stay refused. A watch armed by hand as `( gzcoord-inbox ... & )` has no claude
ancestor, so it is recorded `detached`: that was the no-exit stray.

**Why:** the first version signalled every two-line holder; the review (F1, P2) showed one under a live session's claude is not
provably an orphan. Order matters: the start-time refusal comes before the `detached` branch.
**How to apply:** a mutation that survives (here `ended=pid` in REPLACE_SIGNALLED: signalled pid == holder pid in the deaf case)
means the fixture cannot tell the two values apart: revert the unrequested change or build a fixture with distinct values.
Also: `fabric-review brief` base is origin/main's tip, post-review refuses until it is an ancestor, so merge main before the
brief; a re-review request needs `range` pinned to the reviewed head and `card_base` set. Never arm a watch with a bare `&`.

*Anchors: `tools/fabric/gzcoord/inbox_parts/watchlock.py::replaceable_of`*

*Observed 2026-11-14 (python-dev)*
