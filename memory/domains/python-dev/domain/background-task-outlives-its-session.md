---
role: "python-dev"
class: domain
topic: "background-task-outlives-its-session"
description: "the harness does not kill a background command when its session ends; a long-lived process that holds a lock must tie its life to the session"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fbdf949d83150b7d
---

## the harness does not kill a background command when its session ends; a long-lived process that holds a lock must tie its life to the session

A `gzcoord-inbox --until-delivery` watch kept running after its session was relaunched,
was reparented to systemd --user, held its flock, refused the new session's watch
(ALREADY_RUNNING) and took deliveries nobody read (2026-10-20). Fixed in #347: the watch
records the session process it serves at start and ends when that process is gone or
getppid() changed; a new watch ends an orphan.

**Why:** a flock lives as long as the process; nothing else ties that to the session.

**How to apply:** any daemon-like tool of mine that holds a lock or consumes a queue
records its owner at start and checks it in its wait loop, and a test kills the owner
and expects the exit. Related: [[watch-pins-modules-at-start-j162]].

*References: watch-pins-modules-at-start-j162*

*Observed 2026-10-25 (python-dev)*
