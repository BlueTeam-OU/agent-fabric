---
role: "fabric-coordinator"
class: solution
topic: "control-plane-daemon"
description: "Fleet facts come from fabric-ctl (a control agent per account, tools/fabric/control/agentd.py); the Node agent and agentd.json are gone"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
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
  - c9b713723e8e5a1e
  - d0f75075ca6d9001
---

## Fleet facts come from fabric-ctl (a control agent per account, tools/fabric/control/agentd.py); the Node agent and agentd.json are gone

Fleet facts in real time come from `fabric-ctl all status` (a control agent per account on the relay's `fabric:control` channel, ADR-029; channel config `runtime/control/config.json`; `docs/live-checks/2026-09-17-control-plane.md`), not from sudo loops. `fabric-usage` is the fallback when the agents are down.

There is one implementation now: the ADR-040 Wave 8 cutover finished. `runtime/control/agentd.json` and the Node `agentd.mjs` no longer exist; every account runs `tools/fabric/control/agentd.py` on `/usr/local/bin/fabric-python`. `tools/fabric/bootstrap.py` writes the unit (`runtime/control/agent-fabric-agentd.service`, built with `tools/fabric/agentd_unit.py`). The cutover record is `docs/live-checks/2026-10-09-agentd-cutover.md`. Debug an op in `tools/fabric/control/ops/`.

**How to apply:** a `no answer` row means that account's agent is down or on old code. Restart it with `fabric-host <host> run --as <login> -- bash -lc 'XDG_RUNTIME_DIR=/run/user/$(id -u) ~/projects/agent-fabric/runtime/claude-code/bootstrap.sh'` (the executor's environment is empty, so `systemctl --user` needs the runtime dir spelled out). The agent restarts itself on a pull of its source ("source changed" in agentd.py); a request posted while it was down is never answered. CI runs as `runner`: never assert this host's login in a test.

*Observed 2026-10-11 (fabric-coordinator)*
