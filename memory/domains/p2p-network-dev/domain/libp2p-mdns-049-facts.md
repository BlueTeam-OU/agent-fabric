---
role: "p2p-network-dev"
class: domain
topic: "libp2p-mdns-049-facts"
description: "libp2p-mdns 0.49 (and if-watch 3.2.2 under it): three unbounded remote-fed stores, unsolicited responses accepted, failures only logged, addresses logged at INFO, a refresh extends expiry silently; multicast does not loop back on a shared…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8b49296b93e99dea
---

## libp2p-mdns 0.49 (and if-watch 3.2.2 under it): three unbounded remote-fed stores, unsolicited responses accepted, failures only logged, addresses logged at INFO, a refresh extends expiry silently; multicast does not loop back on a shared interface and the crate skips loopback, so test in `unshare -rn` with a dummy interface (ubuntu-latest needs the apparmor userns sysctl)

Read from the locked source and measured while vendoring it (InterWeave
ADR-0053, 2026-09-23..25):

- **Unbounded, remote-fed:** `discovered_nodes` (SmallVec, linear find —
  quadratic CPU), per-interface `discovered`, and `send_buffer`, appended on
  every received QUERY (a flood is amplified onto the LAN). Unpatched flood:
  65,536 of 65,536 records held, ~213 µs per new record, ~14.5 MB.
- **Announcer picks the TTL**, so a soonest-expiry eviction is a hole unless
  TTL is clamped at intake; a clamp below the default query interval (300 s)
  makes a quiet LAN expire and rediscover in a loop — query interval must
  stay below the clamp (InterWeave: 90 s under a 120 s clamp).
- **Refresh is silent:** a re-seen record only extends its expiry and emits
  nothing, so a consumer with a shorter TTL forgets a live peer unless
  something re-pushes the crate's live records (InterWeave: every half TTL).
- Unsolicited responses are accepted (RFC 6762 §8.3 — not a bug); a receive
  error ends the interface task silently; bind/join/send failures are only
  logged; "discovered/expired peer on address" is logged at INFO with the
  refused address. Rate-limit answers per record per interface (RFC 6762 §6),
  not one slot per interface, or a meta-query starves the peer answer.
- **if-watch 3.2.2** returns `Ready(Err)` on every poll once its netlink
  connection dies, so `while let` over it spins: treat consecutive errors as
  a dead watcher, report once, rebuild at a bounded cadence.
- **Testing:** a packet to 224.0.0.251 over a host interface did not loop
  back in 2 s, and the crate skips loopback (behaviour.rs:286), so the real
  path needs `unshare -rn` plus `ip link add type dummy` (no root, no
  modprobe). GitHub ubuntu-latest 24.04 refuses `uid_map` until
  `sysctl kernel.apparmor_restrict_unprivileged_userns=0`; the test must
  FAIL, not skip, where namespaces are missing.

Related: [[enumerate-a-behaviours-toswarm-emissions]],
[[replacing-a-libp2p-behaviour-leaks-its-tasks]],
[[a-mirroring-store-takes-the-providers-shape-and-aging]].

*References: a-mirroring-store-takes-the-providers-shape-and-aging, enumerate-a-behaviours-toswarm-emissions, replacing-a-libp2p-behaviour-leaks-its-tasks*

*Observed 2026-10-18 (p2p-network-dev)*
