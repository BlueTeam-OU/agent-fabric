---
role: "p2p-network-dev"
class: domain
topic: "domain-libp2p-reuse-dial-eaddrinuse"
description: "libp2p-tcp's port-reuse dial falls back only on EADDRNOTAVAIL; EADDRINUSE fails the dial; kad's own dials are Reuse and a built DialOpts cannot change port use"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 8d6a0cf8fccc1de2
---

## libp2p-tcp's port-reuse dial falls back only on EADDRNOTAVAIL; EADDRINUSE fails the dial; kad's own dials are Reuse and a built DialOpts cannot change port use

- **The fallback gap.** libp2p-tcp 0.45 retries a `PortUse::Reuse` dial on a fresh port only when connect answers EADDRNOTAVAIL (src/lib.rs, the `AddrNotAvailable` arm). On GitHub's ubuntu-24.04 runner the listen-port bind failed with EADDRINUSE (os error 98), so the dial just failed.
  - Seen as intermittent loopback "not connected within 20s" and Kademlia-walk timeouts, InterWeave CI 2026-10-11 and 2026-10-14.
  - Not reproducible on a 6.17 kernel: TIME_WAIT, reuse-address and reuse-port sockets, a second dial from the same port, and parallel load all failed to trigger it.
- **libp2p-kad 0.49's own dials are `DialOpts::peer_id(p).build()`.** That means Reuse by default. A built `DialOpts` exposes no port-use setter (`pub(crate)`), so moving them to a fresh port means rebuilding them (`allocate_new_port`), which mints a new ConnectionId.
- **Hole punches** dial with `role == Endpoint::Listener`. That is how a transport can tell a punch from an ordinary dial.
- **Fix in InterWeave (2026-10-14):** a `port_fallback` transport wrapper, Kademlia and AutoNAT on fresh ports, and CONNECTIVITY.md §12 A 2026-10-14.
- **Diagnose first.** A CI connect helper that ignores OutgoingConnectionError hides the errno. Make it fail fast with the error, then re-run CI until it fails.

*Observed 2026-10-14 (p2p-network-dev)*
