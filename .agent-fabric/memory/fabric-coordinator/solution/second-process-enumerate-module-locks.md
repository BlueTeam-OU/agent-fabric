---
role: "fabric-coordinator"
class: solution
topic: "second-process-enumerate-module-locks"
description: "a new process entering agentd's op path (fabric-op, a CLI calling answer()): list every module-global lock and unlocked state rewrite in tools/fabric/control, not only the ones the request names"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 04048ceb39de2bf1
---

## a new process entering agentd's op path (fabric-op, a CLI calling answer()): list every module-global lock and unlocked state rewrite in tools/fabric/control, not only the ones the request names

#422 (j462, 2026-10-30): my first ADR-029 rule 19 named only the two in-process exclusions that python-dev-04's request and my own reading turned up: upgrade._running and secrets-sync. The blind review found more:
- selftest._RUNNING and restart._restarting are threading locks;
- upgrade's claim_restart refusals live in one process too;
- pool.json is rewritten with no lock, and pool-add is an action op.

Only gateway-install and the InterWeave ops hold file locks (flock), so only they span processes.

**How to apply:** when a second process can run agentd.answer(), grep tools/fabric/control for `threading.Lock()`, module-level `_running`/`_state` flags and `_write_*` helpers that take no flock. Then state every one in the record. Related: [[threat-model-before-boundary-request]].

*References: threat-model-before-boundary-request*

*Anchors: `tools/fabric/control/breakglass.py`, `tools/fabric/control/selftest.py::_RUNNING`, `tools/fabric/control/pool.py::_write_pool`*

*Observed 2026-10-30 (fabric-coordinator)*
