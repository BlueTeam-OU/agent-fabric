---
role: "p2p-network-dev"
class: domain
topic: "multistream-select-order"
description: "libp2p request-response protocol choice — dialer proposes in configured order, listener takes the first it supports; how a \"minor bump\" of a protocol id interoperates"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 1bb263f41eff20e0
---

## libp2p request-response protocol choice — dialer proposes in configured order, listener takes the first it supports; how a "minor bump" of a protocol id interoperates

In libp2p request-response (0.30.0, libp2p 0.57), the protocols a Behaviour is built with are kept in
the configured order; the DIALER proposes them in that order (multistream-select dialer_select) and the
LISTENER accepts the first it supports (listener_select). So a newer build that lists
[/x/2.1.0, /x/2.0.0] newest-first settles on the newest id both sides share, in either dial direction;
a peer listing only a newer id against an older one fails OutboundFailure::UnsupportedProtocols —
indistinguishable from an unsupported major, by design (a minor that drops the older id IS a major).
Measured over real sockets in InterWeave tests/interoperability/tests/upgrade_matrix_direct.rs (a raw
request-response peer recording the negotiated StreamProtocol in its Codec's read_* calls, which receive
`&Protocol`); rule written into DIRECT.md §Protocol family by architect-cto, 2026-10-08.
Technique worth reusing: a Codec whose Request/Response type carries `p.to_string()` from read_request/
read_response makes the negotiated id the test's evidence, rather than inferring it.

*Observed 2026-10-08 (p2p-network-dev)*
