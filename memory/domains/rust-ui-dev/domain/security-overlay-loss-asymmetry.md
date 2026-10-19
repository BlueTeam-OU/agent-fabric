---
role: "rust-ui-dev"
class: domain
topic: "security-overlay-loss-asymmetry"
description: "Judging a security setting that does not survive a restart -- a lost revoke silently re-admits, which honest copy does not fix"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 496f6aa22571f2c3
---

## Judging a security setting that does not survive a restart -- a lost revoke silently re-admits, which honest copy does not fix

When an admin change made in the client is a runtime overlay lost at the service's restart,
the two directions differ: a lost allow fails visibly the next time it is used, but a lost
revoke silently re-admits the peer, and the settings screen then reads the service's list
with nothing marking it as one the person removed. Copy that says "until the service
restarts" is honest but only protects someone who remembers it. Bring the asymmetric case to
the deciding role as a finding with options; the one taken was persisting the overlay of
deltas in the service's state, shown per row as configured vs added here, with an E2E proof
that a revocation survives a restart.

*Observed 2026-10-15 (rust-ui-dev)*
