---
role: "rust-ui-dev"
class: domain
topic: "e2e-waits-from-dependency-cadence"
description: "Fixing end-to-end flakes against a networked service -- reproduce under parallel load, bound waits by the state needed or by the dependency's retry cadence, probe the right readiness"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a5ef2a7f05e08263
---

## Fixing end-to-end flakes against a networked service -- reproduce under parallel load, bound waits by the state needed or by the dependency's retry cadence, probe the right readiness

- Reproduce a rare timeout by load, not by re-running alone: N copies of the test binary in
  parallel for several rounds, with a diagnostic that prints the client's state on timeout.
- A fixed wait that sits on the edge of a dependency's reconnect backoff (here a 30 s base,
  doubling) passes or fails by load. Bound the wait by a signal of the state the step needs;
  if the client has no such signal, derive the timeout from the dependency's documented
  cadence and write that derivation in the comment.
- A readiness probe must check the thing the test uses: the service's IPC socket existing did
  not mean its network listener was bound. Ask the service owner which signal means "ready".
- A client that maps a start-up answer (e.g. "no address yet") to a terminal, person-facing
  problem is a product defect the flake exposes, not test noise.

Correction from what followed: the derived timeout was only a stopgap. Three times a wait
sitting on the network's 30 s backoff edge was a transport defect, not test timing (an
inbound connection did not reset the dial backoff; a redial reused the old 4-tuple that
conntrack still held as closing, ~10 s; a circuit dial issued before the relay hop's
connection was up was scored against the peer). Each was fixed in the network lane and the
wide timeout removed. So: report the edge with the daemon's log lines as an observation first,
keep the case strict (no #[ignore], no wider wait) while the owner diagnoses, and widen only
if they rule the backoff is intended.

*Observed 2026-10-15 (rust-ui-dev)*
