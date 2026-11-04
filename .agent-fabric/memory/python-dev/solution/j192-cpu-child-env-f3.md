---
role: "python-dev"
class: solution
topic: "j192-cpu-child-env-f3"
description: "cpu_child_env TEST_JOBS_ENV rule and the length-cap trap; F3 merged in #429, F6 follows (j193)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b5c9aa045ab879b1
---

## cpu_child_env TEST_JOBS_ENV rule and the length-cap trap; F3 merged in #429, F6 follows (j193)

`tools/fabric/lease.py cpu_child_env`: AGENT_FABRIC_TEST_JOBS unset/empty -> slot jobs, number above budget -> lowered with a line, 0 and non-numbers kept. d7d1ee32 added `len(have) >= 10` as "above budget" to keep int() off 5000 digits (ValueError past 4300 digits) — but that wrongly replaces zero-padded values like 0000000002 (round-2 F6, j193).

**Why:** a length test stands in for a magnitude test only after leading zeros are stripped.
**How to apply:** strip leading zeros (lstrip("0")) before the length test, then compare; test zero-padded low, zero-padded 0, and 5000 digits, mutation-checked. Supplied via for/ branch off origin/main, REPLY to the coordinator.

*Observed 2026-10-30 (python-dev)*
