---
role: "p2p-network-dev"
class: domain
topic: "domain-an-admission-refusal-is-established-then-closed"
description: "When peer admission is decided after the Noise handshake, a refused peer's dial is established and then closed: a 'not connected before trust' control asserts no message admitted, not no connection"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 0b0ab589a6975023
---

## When peer admission is decided after the Noise handshake, a refused peer's dial is established and then closed: a 'not connected before trust' control asserts no message admitted, not no connection

A node can classify a peer only after Noise has authenticated its PeerId. So the earliest refusal of an
untrusted inbound is to close the connection at, or just after, establishment. TCP and Noise complete first, and
no protocol is offered in between. architect-cto said in REPLY 01a16e31 that the repository has held this since
Stage 11; the design is in SECURITY.md's connectivity admission section, and grep found no single sentence there
on 2026-10-25. Measured on stand-ins
(173f4dfb) and on two phones (#417 row 2, step 2): with A trusting B and B not trusting A, nothing crossed either
way, but A's peer row ended `connected` once and `denied` otherwise.

architect-cto ruled (REPLY 01a16e31) that a gate saying peers "connect ... and not before" means a connection the
data plane admits, on which a message crosses. The handshake the untrusted side closes IS the refusal.

**How to apply:** in a negative control for trust or admission, assert that no message is accepted (or that the
data plane never admitted the connection). Do not assert that no connection was ever up, or the test is flaky.
Do not name a test "never connects" either, or the review finds the overclaim. When a gate's wording reads
stricter than the design can meet, ask its owner for the reading before the run file decides it. Related:
[[workflow-a-run-file-fix-sweeps-every-restatement]].

*References: workflow-a-run-file-fix-sweeps-every-restatement*

*Observed 2026-10-25 (p2p-network-dev)*
