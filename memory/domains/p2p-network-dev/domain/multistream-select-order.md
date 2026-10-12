---
role: "p2p-network-dev"
class: domain
topic: "multistream-select-order"
description: "libp2p request-response protocol choice — dialer proposes in configured order, listener takes the first it supports; re-checked 2026-10-11, unchanged"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 1bb263f41eff20e0
  - 31fb5e20da501255
---

## libp2p request-response protocol choice — dialer proposes in configured order, listener takes the first it supports; re-checked 2026-10-11, unchanged

In libp2p request-response (0.30.0, libp2p 0.57), the protocols a Behaviour is built with are kept in configured order. The DIALER proposes them in that order (multistream-select dialer_select), and the LISTENER accepts the first it supports (listener_select).
- A newer build that lists [/x/2.1.0, /x/2.0.0] newest-first settles on the newest id both sides share, in either dial direction.
- A peer listing only a newer id against an older one fails OutboundFailure::UnsupportedProtocols. That is indistinguishable from an unsupported major, by design: a minor that drops the older id IS a major.

Measured over real sockets in InterWeave's tests/interoperability/tests/upgrade_matrix_direct.rs, which exists on InterWeave origin/main as of 2026-10-11. The check that flagged the path read it against agent-fabric's tree, not InterWeave's. The test uses a raw request-response peer that records the negotiated StreamProtocol in its Codec's read_* calls (`protocol: p.to_string()`). architect-cto wrote the rule into DIRECT.md §Protocol family on 2026-10-08.

Technique worth reusing: a Codec whose Request/Response type carries `p.to_string()` from read_request/read_response makes the negotiated id the test's evidence, rather than inferring it.

*Observed 2026-10-11 (p2p-network-dev): re-checked against InterWeave origin/main.*

*Observed 2026-10-11 (p2p-network-dev)*
