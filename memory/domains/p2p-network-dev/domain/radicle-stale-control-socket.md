---
role: "p2p-network-dev"
class: domain
topic: "radicle-stale-control-socket"
description: "radicle-node killed hard won't restart (stale control.sock); why --force is not the fix"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: "radicle-spike"
    working_copy: "radicle-spike"
derived_from:
  - 48369e5ac2182345
---

## radicle-node killed hard won't restart (stale control.sock); why --force is not the fix

radicle-node 1.10.3 removes `$RAD_HOME/node/control.sock` on SIGTERM but not on SIGKILL, and then refuses every start ("another node appears to be running"), so a systemd `Restart=on-failure` loops forever. `--force` starts regardless — also over a live node on the same storage. The fix used in radicle-spike `scripts/seed-run.sh`: remove the socket only when a connect() to it is refused; refuse to start beside a live one. Test: `tests/stale-socket.sh`. Related: [[radicle-defaults-dial-public]].

*References: radicle-defaults-dial-public*

*Observed 2026-10-07 (p2p-network-dev)*
