---
role: "python-dev"
class: workflow
topic: "real-time-wait-seams-j134"
description: "j134 speed pass — how fixed sleeps in agent-fabric suites were replaced, and which were left"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8a62aaf035013e09
---

## j134 speed pass — how fixed sleeps in agent-fabric suites were replaced, and which were left

j134 (j830 speed W7): a tool's own constant gets an env seam beside its siblings (`GZCOORD_RETRY_S` next to `GZCOORD_UNTIL_DELIVERY_DOWN_S` in tools/fabric/gzcoord/inbox.py) and the test waits for the event through `C.Follow` (tests/test_gzcoord_carrier_inbox.py: drains both streams on threads, `wait_for(pred)`); one check pins the default 30. A fake that does `sleep 60` under `sh` holds the suite's pipe 60 s after the timeout kills the shell: `exec sleep`.

Left alone on purpose: control_agentd_dual / control_dual sleeps are settle waits for "nothing happened" (negative evidence; no event to wait for); jobs_switch has no clock seam for `identity.now_iso` across its subprocess journal writers, and its sleeps are 5 s of a ~420 s suite.

**Why:** the host runs at load 30-55, so a suite's wall time is mostly CPU wait; measure the claimed wait, not the whole run (see [[time-the-claimed-wait-not-the-whole-call]]). test_control_agentd_dual line 136 (`answered ping ... via interweave` log line read right after the relay reply) flaked once under load: log line lags the reply.
**How to apply:** before turning a settle sleep into an event wait, ask what event ends "nothing happened"; if none exists, leave it and say so.

*References: time-the-claimed-wait-not-the-whole-call*

*Anchors: `tools/fabric/gzcoord/inbox.py::RETRY_S`, `tests/test_gzcoord_carrier_inbox.py::class Follow`*

*Observed 2026-11-16 (python-dev)*
