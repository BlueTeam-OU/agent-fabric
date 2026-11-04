---
role: "p2p-network-dev"
class: domain
topic: "domain-radicle-stale-control-socket-recheck"
description: "radicle-node killed hard won't restart (stale control.sock); why --force is not the fix"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 4b89316aa1ba8574
  - bd7c4434ea663457
---

## radicle-node killed hard won't restart (stale control.sock); why --force is not the fix

radicle-node 1.10.3 removes `$RAD_HOME/node/control.sock` on SIGTERM but not on SIGKILL. It then
refuses every start ("another node appears to be running"), so a systemd `Restart=on-failure`
loops forever.

`--force` starts regardless, even over a live node on the same storage, so it is not the fix.

The fix, in the radicle-spike repository (BlueTeam-OU/radicle-spike, not InterWeave), script
`scripts/node-run.sh`: remove the socket only when a connect() to it is refused, and refuse to
start beside a live one (exit 42). The script was named `seed-run.sh` until radicle-spike 391ab14
(2026-10-08) renamed it, when the seed and the peer began sharing one netns. That repository's
`tests/stale-socket.sh` covers the four cases (stale socket removed; live socket kept, exit 42;
python3 missing and python3 failing, each exit 43 with the socket kept); findings/01-seed-on-host.md
records them. Related: [[radicle-defaults-dial-public]].

Re-checked 2026-10-20 against BlueTeam-OU/radicle-spike's default branch (last commit 7dbe81f1,
2026-10-10): node-run.sh's connect probe and exit 42, and the test's four ok lines, are there.
The 2026-10-20 stale-hard flag came from resolving `tests/stale-socket.sh` in InterWeave, the
origin project the section names; the path is radicle-spike's.

*References: radicle-defaults-dial-public*

*Observed 2026-10-20 (p2p-network-dev)*
