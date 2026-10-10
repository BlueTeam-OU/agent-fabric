---
role: "fabric-coordinator"
class: solution
topic: "control-plane-daemon"
description: "Fleet facts come from fabric-ctl (a control agent per account); runtime/control/agentd.json says which implementation each account runs"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 2b89e2828548489c
  - 60b07e29d8d071e2
  - d0f75075ca6d9001
---

## Fleet facts come from fabric-ctl (a control agent per account); runtime/control/agentd.json says which implementation each account runs

Fleet facts in real time come from `fabric-ctl all status` (a control agent per account on the relay's `fabric:control` channel, ADR-029; `docs/live-checks/2026-09-17-control-plane.md`), not from sudo loops. `fabric-usage` is the fallback when the agents are down.

Two implementations exist during the ADR-040 Wave 8 cutover: `runtime/control/agentd.json` names, per login, the Node agent (`runtime/control/agentd.mjs`) or the Python one (`tools/fabric/control/agentd.py`, on `/usr/local/bin/fabric-python`); `tools/fabric/bootstrap.py` writes the unit's ExecStart from it, and `fabric-status` prints `agentd python|node` and any DRIFT (`docs/live-checks/2026-10-09-agentd-cutover.md`). Read the right tree when debugging an op.

**How to apply:** a `no answer` row means that account's agent is down or on old code. Restart it with `fabric-host <host> run --as <login> -- bash -lc 'XDG_RUNTIME_DIR=/run/user/$(id -u) ~/projects/agent-fabric/runtime/claude-code/bootstrap.sh'` (the executor's environment is empty, so `systemctl --user` needs the runtime dir spelled out). An agent restarts itself on a pull of its source ("source changed", both implementations); a request posted while it was down is never answered. CI runs as `runner`: never assert this host's login in a test.

*Observed 2026-10-10 (fabric-coordinator)*
