---
role: "p2p-network-dev"
class: domain
topic: "radicle-replication-facts"
description: "Radicle 1.10.3 replication and reachability facts measured in radicle-spike (lag, clone timeout, NAT, netns)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: "radicle-spike"
    working_copy: "radicle-spike"
derived_from:
  - 651bc4ea614b71b7
---

## Radicle 1.10.3 replication and reachability facts measured in radicle-spike (lag, clone timeout, NAT, netns)

Measured 2026-10-08 in radicle-spike (findings/03-replication.md):
- A peer connected to a seed fetches on the seed's ref announcement: each of 7 pushes into the seed (via git-remote-rad) was in the peer 0.09–0.37 s before the pushing process even exited. No polling.
- `rad clone` waits 30 s by default (DEFAULT_TIMEOUT, crates/radicle/src/node/command.rs) and fails "timed out reading from control socket" at 400 ms RTT for a 12 MB repo; `--timeout 5min` → ~40 s, ok. The node's fetchTimeout did not bind.
- A fresh node can't clone until it has connected and heard the seed's inventory ("no candidate seeds were found"): 0.6–2.3 s; wait on `rad node routing --rid … --json` holding the seed.
- No NAT traversal at all (no UPnP, hole punching, STUN/TURN); `relay` is gossip re-announcement. Transport: TCP + Noise XK, or Tor/I2P via proxy.
- Unprivileged: a user unit can hold a loopback-only userns+netns (`unshare -rn … sleep infinity`); nodes join with `nsenter -t <pid> -U -n --preserve-credentials`; `tc netem` works inside it without root.
- systemd: nodes BindsTo= a namespace-holder unit are left stopped when the holder crashes and auto-restarts. Fix with Wants= on the holder (each holder start, auto-restart included, starts them); not Upholds=, which restarts a node whenever it is down and so overrides RestartPreventExitStatus and undoes a manual stop (measured live, radicle-spike #4).
- In a clone only the default branch is canonical (rad/main); other branches appear as `<alias>@<nid>/<branch>` remote-tracking refs.
Related: [[radicle-defaults-dial-public]], [[radicle-stale-control-socket]].

*References: radicle-defaults-dial-public, radicle-stale-control-socket*

*Observed 2026-10-08 (p2p-network-dev)*
