---
role: "p2p-network-dev"
class: workflow
topic: "a-second-uid-measurement-is-a-second-agents-run"
description: "A measurement that needs a second Linux account (port sharing, per-uid limits, a second user manager) is run by another agent in its own account, coordinated by REQUEST with exact steps and a stop condition, never by a shell or key into…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0be2c25ad2eec7e3
---

## A measurement that needs a second Linux account (port sharing, per-uid limits, a second user manager) is run by another agent in its own account, coordinated by REQUEST with exact steps and a stop condition, never by a shell or key into another account

fabric-coordinator refused an SSH shell into a test account (decision,
2026-10-27): one agent acting in a second account breaks "the login is
the agent" (agent-fabric ADR-038) and ADR-048's sshd door; sudo -u/su
give no user manager or XDG_RUNTIME_DIR anyway. The route that worked:
the role's other holder, in its own account, ran the steps.

**How to apply:**
- Hold your side (the port, the unit) first, then send a REQUEST with
  numbered steps, the expected output of each, and a stop condition:
  "if your account already runs <the thing> for another purpose, stop
  before installing and tell me". The other holder's account was
  running the fleet's carrier on the same build, and stopping there
  saved its live units.
- Run the control as a timed handoff: you stop, say the time, they
  read the next retry (bound one second later here).
- Record what the route did not exercise (here: a fresh install from
  the archive) by name in the evidence.

*Observed 2026-10-31 (p2p-network-dev)*
