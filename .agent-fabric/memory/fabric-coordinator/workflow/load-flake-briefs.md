---
role: "fabric-coordinator"
class: workflow
topic: "load-flake-briefs"
description: "Timing reds under host load: check uptime and re-run the suite alone before calling it a defect; a fix waits on state or CPU time, never wall time; reproduce start-up flakes by delaying interpreter start, and show fail-before/pass-after…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c22cf57be6853075
---

## Timing reds under host load: check uptime and re-run the suite alone before calling it a defect; a fix waits on state or CPU time, never wall time; reproduce start-up flakes by delaying interpreter start, and show fail-before/pass-after counts

On develop-qzapp the load often sits at 46-78 on 10 cores. Suites that failed only on timing passed alone in the same environment. A wall-clock case failed 103 of 150 tries at load 60 but never when bounded on CPU time. CPU load alone (30 busy loops) did not reproduce the start-up flakes; a 3 s interpreter start delay did.

A case asserting one limit fires "well under" another limit cannot hold under load. The fix that held on #364: for that one call, raise every other limit far out of reach (the wall ceiling to 120 s), so only the limit under test can answer, and keep a control with that limit removed.

**Why:** a wall bound on a process a loaded host starves fails without any race; sending it back as a defect wastes a supplier round.
**How to apply:** on a timing-only red, run `uptime`, re-run that suite alone and compare with CI. A fix request asks for a wait on state or CPU time, names any bound in fenced code instead of editing it, and asks for a before/after loop with counts. A start-up flake is reproduced with a sitecustomize on PYTHONPATH that delays start. Seen 2026-10-25 at load ~70 (j388, #371 head 6d26687a): four python modules ended at the 900 s budget in the full run and passed alone; test_gzcoord_carrier_engine failed a *different* check alone, then passed twice on the head and once on origin/main. A different check failing each run is the load signature; one control run on origin/main in a detached worktree settles "not mine". Related: [[fold-then-full-suite]], [[suite-verdict-not-pipeline-exit]].

*References: fold-then-full-suite, suite-verdict-not-pipeline-exit*

*Observed 2026-10-25 (fabric-coordinator)*
