---
role: "fabric-coordinator"
class: solution
topic: "control-config-picks-keys"
description: "a new key in runtime/control/config.json reaches no caller unless agentd.control_config() carries it — it returns a picked-keys dict, not the file"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2b8d13b1d54ba05b
---

## a new key in runtime/control/config.json reaches no caller unless agentd.control_config() carries it — it returns a picked-keys dict, not the file

`tools/fabric/control/agentd.py::control_config()` builds a fresh dict of named keys
(relay_url, channel, state_channel, ttl_s, and since agent-fabric#564 pool_holder).
Every control caller (agentd pool ops, ctl.py, queue.py) reads that dict, never the
file, so a key added only to `runtime/control/config.json` is silently ignored.
Seen 2026-11-12: I set `pool_holder` for the two-host fleet (fabric-h2 joined) and the
review found the pool still had no holder (#564 F1, fixed 4508ac4f).

**How to apply:** when adding a config key, add it to control_config() and test it
through control_config(), not through a hand-made dict; read it back with
`pool.pool_holder(agentd.control_config(env={}))`-style calls from tools/fabric.

*Anchors: `tools/fabric/control/agentd.py::control_config`, `tools/fabric/control/pool.py::pool_holder`*

*Observed 2026-11-12 (fabric-coordinator)*
