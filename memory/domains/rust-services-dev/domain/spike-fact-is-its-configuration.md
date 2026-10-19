---
role: "rust-services-dev"
class: domain
topic: "spike-fact-is-its-configuration"
description: "a spike's wire observation describes the client configuration it ran; check it in the configuration the gateway serves and commit it to the record before a contract relies on it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 2b7b70d29ab4a9c5
---

## a spike's wire observation describes the client configuration it ran; check it in the configuration the gateway serves and commit it to the record before a contract relies on it

What a harness sends depends on how the spike configured it, not only on the backend. Two cases on the Codex spike:
- "The ChatGPT backend needs a WebSocket" was reported, then retracted eight minutes later. The WebSocket was the built-in
  provider's preference. The pinned source and a turn through a custom provider showed that plain HTTPS works.
- The spike recorded `POST /v1/responses` only because its runner's base URL ended in `/v1`. A contract inventory then needed a
  separate run with a root base to show `POST /responses`.

A wire fact that a contract relies on and that lives only in a message is flagged in review: it cannot be checked from the tree.

**Why:** a wrong requirement sent to the records' holder (here, "admit WebSocket") reaches a decision and costs a correction round.

**How to apply:** record the client configuration (provider, base URL and path, flags) beside every wire fact. Before reporting
anything as a backend requirement, read the pinned client's source and run the configuration the gateway will actually serve.
Put a run you make for someone else into the spike's script as a knob and into its README, in the same PR.
[[codex-spike-recipe]]

*References: codex-spike-recipe*

*Observed 2026-10-15 (rust-services-dev)*
