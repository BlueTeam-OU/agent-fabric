---
role: "python-dev"
class: workflow
topic: "shell-ports-only-with-a-real-change"
description: "before proposing to port a shell script to Python — under ADR-040's 150-line bound, a script is ported only with a substantial change it needs"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3bd002f1d545f2e6
---

## before proposing to port a shell script to Python — under ADR-040's 150-line bound, a script is ported only with a substantial change it needs

A shell script under ADR-040's 150-line bound is ported to Python only
when it next needs a substantial change, never for its own sake. This is
the owner's rule of 2026-09-29, restated by fabric-coordinator on
2026-10-06 when it declined five candidates I proposed: hostexec and
worker, fabric-host, rename-working-copy.sh, moveto, persist-accounts.sh.
The REQUEST that asks for the change asks for the port with it.

**Why:** every port of a working script costs a review and a rollout to
every host. hostexec, moveto and persist-accounts sit on the paths with
the most blast radius: every host operation, login, boot.
**How to apply:** do not propose ports as standalone work. When a
REQUEST changes one of these scripts substantially, offer the port in
the plan reply. The coordinator agreed on the order: hostexec and
fabric-host as one module first, then rename-working-copy.sh. With an
empty job list, wait for a REQUEST; do not pick work from the backlog.

*Observed 2026-10-06 (python-dev)*
