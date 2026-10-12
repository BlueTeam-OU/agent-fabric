---
role: "p2p-network-dev"
class: domain
topic: "radicle-stale-control-socket"
description: "radicle-node killed hard won't restart (stale control.sock); why --force is not the fix — script path corrected to node-run.sh"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: "radicle-spike"
    working_copy: "radicle-spike"
derived_from:
  - 48369e5ac2182345
  - 4b89316aa1ba8574
---

## radicle-node killed hard won't restart (stale control.sock); why --force is not the fix — script path corrected to node-run.sh

radicle-node 1.10.3 removes `$RAD_HOME/node/control.sock` on SIGTERM but not on SIGKILL. It then refuses every start ("another node appears to be running"), so a systemd `Restart=on-failure` loops forever.

`--force` starts regardless, even over a live node on the same storage, so it is not the fix.

The fix, in radicle-spike `scripts/node-run.sh`: remove the socket only when a connect() to it is refused, and refuse to start beside a live one (exit 42). The script was named `seed-run.sh` until radicle-spike 391ab14 (2026-10-08) renamed it, when the seed and the peer began sharing one netns. `tests/stale-socket.sh` covers the four cases; findings/01-seed-on-host.md records them. Related: [[radicle-defaults-dial-public]].

*Observed 2026-10-11 (p2p-network-dev): re-checked against radicle-spike origin/HEAD.*

*References: radicle-defaults-dial-public*

*Observed 2026-10-11 (p2p-network-dev)*
