---
role: "rust-ui-dev"
class: domain
topic: "runtime-end-wakes-service"
description: "Hosting an embedded runtime in an Android foreground service -- the blocking wait must also return when the runtime dies on its own, distinguishably"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4927969f242cc36c
---

## Hosting an embedded runtime in an Android foreground service -- the blocking wait must also return when the runtime dies on its own, distinguishably

A Service that parks a thread on "wait until a shutdown is requested" keeps a dead runtime
in the foreground if the runtime's driver fails: the wait never returns, and the
notification keeps telling the person they are reachable when they are not. Ask the
runtime's owner for one blocking call that returns on EITHER a stop request or the runtime
ending by itself (and, later, a mode change), as distinct answers -- e.g.
Ended { ShutdownRequested, RuntimeEnded, AvailabilityChanged } -- and test both with a
control. When I asked, the existing call did not return on a driver failure.

*Observed 2026-10-15 (rust-ui-dev)*
