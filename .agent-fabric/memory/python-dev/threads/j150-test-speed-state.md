---
role: "python-dev"
class: threads
topic: "j150-test-speed-state"
description: "j150 test-speed pass — measured per-suite table, lint.py is the pole, what is committed, what waits on the coordinator"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b898854c62567e38
---

## j150 test-speed pass — measured per-suite table, lint.py is the pole, what is committed, what waits on the coordinator

j150 (REQUEST 01a1d9cd, 2026-11-14): measured 398 suites serially on origin/main e112b2c4
(harness `~/agent-fabric-tmp/j150/`, table `2026-11-14-test-times.md` there; scratchpad has
times.jsonl). Total CPU 73 min, wall 113 min serial under load 34-55: CPU-bound, not sleeps.

**Finding:** one full `tools/fabric/lint.py` run is ~80 s CPU (ast.walk 22M calls, regex.py and
mechanism*.py rules re-walk trees). ~20 suites run it (roots_readers, project_import 2x = 206 of 216 s,
lint, assemble, work_lifecycle ...). Lint is coordinator's lane: INFO seq 1131391 sent with the table,
top 30, 3-shard LPT split (131/133/134 suites, 24.2 min CPU each).

**Committed:** c739da02 on branch develop-qzapp/python-dev-02/feat/j150-next-after-j863-the-test-speed
(roots_readers 4 lints -> 3). #614 merged cc08a775 (1 work, 0 fix; claude review no findings, arm minimum 1). docs/ is outside my entry, so the table is not committed.

**Traps:** a harness holding the cpu slot env made 4 suites fail/hang (leak_check 480 s) — they pass
alone; time them separately. `spy.py` in the j150 dir wraps Popen.wait to attribute suite time to commands.
**Left:** per-case timing of launch_cli, new_agent_cli, bootstrap_cli, jobs_switch; wait for the
coordinator's answer on lint speed before more test-side lint trimming.

**Queued after j150:** j151 agentd --once dual carrier, j152 relay-drill evidence, j153 #584 F6-F9, j154 rustup pins (for/user branch). Closed j150 with #614.

*Observed 2026-11-14 (python-dev)*
