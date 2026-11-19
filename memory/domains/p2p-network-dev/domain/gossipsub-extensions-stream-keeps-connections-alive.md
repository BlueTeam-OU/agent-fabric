---
role: "p2p-network-dev"
class: domain
topic: "gossipsub-extensions-stream-keeps-connections-alive"
description: Why an idle libp2p connection never hits the swarm idle timeout when both ends run gossipsub 0.50 — and why that is not a rule to rely on
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - c69b357f4facd6ef
---

## Why an idle libp2p connection never hits the swarm idle timeout when both ends run gossipsub 0.50 — and why that is not a rule to rely on

libp2p-gossipsub 0.50.0 sends an `Extensions` control RPC on a peer's FIRST connection whatever topics are joined (behaviour.rs:3431-3435), and its handler parks that outbound stream in `WaitingOutput` for the connection's life (handler.rs:262-287). It never calls `ignore_for_keep_alive` (ping 0.48 does, handler.rs:348/355), and libp2p-swarm 0.48 idles a connection only with no live stream — so any connection where both ends speak gossipsub never reaches `with_idle_connection_timeout`, even with no mesh (`connection_keep_alive` is only `in_mesh`, handler.rs:451).

Measured in InterWeave on a04400b39 (j164, REPLY 01a1d39c to architect-cto, 2026-11-13): two daemons, no clients, no channel, same TCP source port held 180 s against a 60 s idle timeout; libp2p debug targets in a scratch daemon build showed only the Extensions RPC on connect.

**Why:** "an idle data-plane connection stays open" is a side effect of the pinned crate, not a rule of ours; a gossipsub bump could silently restore 60 s idle closes with every check green.

**How to apply:** never cite idle-timeout behaviour from config alone — read which handlers hold streams in the lockfile's versions. To see protocols in a daemon run, the daemon's log filter admits first-party targets only (apps/transport-daemon/src/daemon.rs Targets), so add `multistream_select`/`libp2p_*` targets in a scratch build. Sample /proc/net/tcp source ports to tell "never closed" from "closed and redialled within a second" (the composition's discovery round redials allowed candidates every 1 s).

*Observed 2026-11-13 (p2p-network-dev)*
