---
role: "python-dev"
class: solution
topic: "own-host-param-and-refresh-recheck-same-class"
description: "j121 #598 carrier: a startup-only check misses the engine's roster refresh; replacing a filtered helper with a CLI call drops the filter"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e64defcefbd35e72
---

## j121 #598 carrier: a startup-only check misses the engine's roster refresh; replacing a filtered helper with a CLI call drops the filter

A check added at carrier start (`cmd_run`) must also sit in `engine.refresh_roster`: the roster is swapped while the carrier runs, and a row admitted after start skips the startup check (review F1 of #598). Put the invariant in one function (`roster.check_own_host`) and call it from both.

Swapping a test's filtered render (`judged_roster` narrowed to two accounts) for a `render-config` subprocess dropped the narrowing (F5); a live-only test that CI cannot run was deferred with `--defer`, so check what a replacement call no longer filters.

**Why:** reviewer found both; the round-2 brief's diff section was shortened by hand and still worked, but retyping is risky ([[rereview-brief-retyped-by-hand-drifts]]).
**How to apply:** when a rule is enforced at a boundary, grep every other path that installs the same state (refresh, reload, swap). Arm refused on open P3s until `--defer "<head8>:F<n>" "<why>"` per finding, label = the head that raised it ([[defer-label-is-the-raising-head-not-the-chain-head]]).

*References: defer-label-is-the-raising-head-not-the-chain-head, rereview-brief-retyped-by-hand-drifts*

*Anchors: `tools/fabric/gzcoord/carrier/roster.py::check_own_host`, `tools/fabric/gzcoord/carrier/engine.py::refresh_roster`*

*Observed 2026-11-14 (python-dev)*
