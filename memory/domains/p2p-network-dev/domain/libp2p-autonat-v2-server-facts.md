---
role: "p2p-network-dev"
class: domain
topic: "libp2p-autonat-v2-server-facts"
description: "libp2p-autonat v2 server (0.15/0.16) — Event.result Ok means the response was sent, including an E_DIAL_BACK_ERROR; the dial outcome is crate-internal; it dials back any address the client asks for; its timeouts are 10 s in code with no…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 87f601b6bedb29d4
---

## libp2p-autonat v2 server (0.15/0.16) — Event.result Ok means the response was sent, including an E_DIAL_BACK_ERROR; the dial outcome is crate-internal; it dials back any address the client asks for; its timeouts are 10 s in code with no setter

Read from the crate (vendored 0.15.0, re-checked at 0.16.0), 2026-09-18:

- **`Event.result` is Ok once the RESPONSE is sent and the stream
  closed** (`server/handler/dial_request.rs` ~240-246), including a
  response whose `dial_status` is `E_DIAL_BACK_ERROR` after a failed
  nonce exchange (~176-183). The dial-back handler's `ToBehaviour` is
  `Ok(())` once the outcome went down an internal `back_channel`,
  whatever it was (`dial_back.rs` ~128-131). So a wrapper sees neither
  the nonce result nor the dial status from public events. A counter
  "served_ok" built on `Decision::Reached && result.is_ok()` counts
  delivered failures, and a failed send after a good dial-back reads as
  not reached. InterWeave fixed it with an additive vendored patch: the
  public Event carries the dial outcome (ADR-0051 Decision 3a).
- **No address-class filter:** the server dials back whatever address
  the client requested, and the client inserts every candidate. A
  crate-level two-Swarm test on loopback therefore works; a substrate
  whose candidate rule refuses loopback cannot be tested there.
- **Timeouts are hard-coded:** request and dial-back streams are bounded
  at 10 s in code with no setter; the dial itself is bounded by the
  Swarm's connection timeout. A config key for a server "probe timeout"
  reaches no mechanism.

**How to apply:** a status field or counter is named for what the code
measures, not for what one hopes it measures; check what an `Ok` in a
libp2p event actually covers before deriving a success metric from it.
Re-read these sites on any autonat bump. See also
[[error-text-matching-pins-the-public-type]].

*References: error-text-matching-pins-the-public-type*

*Observed 2026-10-15 (p2p-network-dev)*
