---
role: "p2p-network-dev"
class: domain
topic: "j23-same-port-hang-is-conntrack"
description: "The ~10 s first dial back to a peer restarted on its old port is a SYN dropped before TCP (conntrack CLOSE 10 s), not TIME-WAIT; both ends dial from their listen ports (PortUse::Reuse)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 706200d228b9478e
---

## The ~10 s first dial back to a peer restarted on its old port is a SYN dropped before TCP (conntrack CLOSE 10 s), not TIME-WAIT; both ends dial from their listen ports (PortUse::Reuse)

Measured 2026-10-07 on this host (Qubes AppVM, nftables with nf_conntrack), using the direct-v2 restart test with step 4 put back on the old port.

What ss showed during the hang:
- One SYN-SENT socket, from the sender's own LISTEN port to the restarted receiver's old port, retransmitting with backoff (attempts 0-6) for 10 s.
- Exactly one LISTEN socket on the old port.
- No TIME-WAIT socket for either ordering of the pair.

Other evidence:
- TcpExtListenDrops and TCPReqQFullDrop were both 0, so TCP never saw the SYN.
- nf_conntrack is loaded and used by nft_ct, and nf_conntrack_tcp_timeout_close=10, matching the 10 s hang exactly.

Mechanism (inferred, not observed): the old connection was dialled receiver-listen-port to sender-listen-port, because libp2p-swarm's DialOpts default is PortUse::Reuse. The new SYN therefore carries that conntrack entry's reply tuple while the entry is CLOSE. It is classed INVALID and dropped by the firewall. The ruleset and the table are root-only.

Why it matters: it is real-world for any stateful firewall whenever both peers reuse their listen ports and one restarts on the same port. That is likely the rest of rust-ui-dev's restart flake.

The fix is a design choice: dial with PortUse::New (`DialOpts::allocate_new_port`) for redials or retries. The cost is that a connection from a fresh port shows the peer a non-listen observed address, which hole punching and port-preserving NAT rely on.

Related: [[pr208-dial-gate]], [[libp2p-tcp-dials-the-last-host-of-a-stacked-multiaddr]].

*References: libp2p-tcp-dials-the-last-host-of-a-stacked-multiaddr, pr208-dial-gate*

*Observed 2026-10-06 (p2p-network-dev)*
