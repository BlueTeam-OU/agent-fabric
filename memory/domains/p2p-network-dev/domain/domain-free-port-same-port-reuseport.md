---
role: "p2p-network-dev"
class: domain
topic: "domain-free-port-same-port-reuseport"
description: "Third shape of the port-0 picker class: a test that makes a 'down' peer address by binding tcp/0 and dropping it can have another test process listen there; the dial then meets a stranger (Unexpected peer ID) and takes the quarantine path…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 20d123f994a98bd4
  - 98150fa31bc82b32
  - a4d5740a7e9ea465
---

## Third shape of the port-0 picker class: a test that makes a 'down' peer address by binding tcp/0 and dropping it can have another test process listen there; the dial then meets a stranger (Unexpected peer ID) and takes the quarantine path instead of the refusal under test

- **Third shape (2026-10-28, #504 and #507):** a "dead" address made
  by binding port 0, reading the port and releasing it is free for
  any other process's port-0 listener. Under nextest on a busy runner
  another test's swarm took it; the reconnect scheduler's dial to the
  "down" relay got `Unexpected peer ID`, the gate quarantined the
  address, and the retry the test waited for never came (merge-queue
  run 40676203372 evicted an unrelated PR). Reproduced locally by
  planting a second listener on the freed port.
- **Fix:** a down address comes from the claiming picker (below the
  port-0 range, claimed across processes) and stays unbound. A port
  that is held open (a black-hole listener) is a different fixture
  and is fine.
- **Diagnose by** a dial to a "down" address that fails with a peer-id
  mismatch rather than connection refused.

*Observed 2026-10-31 (p2p-network-dev)*
