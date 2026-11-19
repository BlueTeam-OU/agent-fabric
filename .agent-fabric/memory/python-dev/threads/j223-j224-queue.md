---
role: "python-dev"
class: threads
topic: "j223-j224-queue"
description: "j223 assembler hygiene refusal, then j224 launcher ff refusal + RESTART text: both undertaken 2026-11-10, one PR at a time"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e2d8414130af209b
---

## j223 assembler hygiene refusal, then j224 launcher ff refusal + RESTART text: both undertaken 2026-11-10, one PR at a time

Two REQUESTs from the coordinator (develop-qzapp/user) on 2026-11-10, both answered with an undertaking (REPLY seq 974913 and 974924).

- j223 (request 01a1c436-6330-7889-8821-6c2c326dd769): tools/fabric/assemble.py refuses a registered project whose .agent-fabric/hygiene.json is not found; `--allow-missing-hygiene` lets it through and the report still names it; tests in tests/test_assemble.py with a control that fails on main. Branch develop-qzapp/python-dev-01/feat/j223-assembler-refuse-a-project-whose-hygiene.
- j224 (request 01a1c436-669a-732c-ab7c-7c7c80b3170e, body via `gzcoord-inbox --replay 974834`): tools/fabric/launch.py (1) fast-forward check refused a clean checkout that `fabric-ctl upgrade fabric` moved; find the cause, test reproduces on main; (2) RESTART NOT COMPLETED text near l.938 must say fabric-resume, then fabric-fresh --job.

**Why:** one open PR per agent and repository, so j224 waits for j223 to merge; each gets its PR number in a REPLY, and an INFO to the coordinator on merge.

**How to apply:** `fabric-jobs show` does not carry a request body; `gzcoord-inbox --replay <seq>` does.

*Observed 2026-11-10 (python-dev)*
