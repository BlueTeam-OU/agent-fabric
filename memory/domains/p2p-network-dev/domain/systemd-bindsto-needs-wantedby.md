---
role: "p2p-network-dev"
class: domain
topic: "systemd-bindsto-needs-wantedby"
description: a client unit BindsTo= its daemon is stopped on a daemon restart and stays down unless WantedBy= the daemon instance
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 02507f6159bc88b2
---

## a client unit BindsTo= its daemon is stopped on a daemon restart and stays down unless WantedBy= the daemon instance

For a client unit with After= and BindsTo= its daemon, add `[Install] WantedBy=<daemon>@%i.service` and enable it. BindsTo= stops the client whenever the daemon stops, an automatic Restart= included. Only the daemon's Wants (from that WantedBy) starts the client again. Measured on a systemd user manager on 2026-10-19 (InterWeave packaging/linux, f68b7b56): after SIGKILL the daemon auto-restarted at RestartSec=5 and the client came back with it. A probe of user units can run under a scratch instance: `systemctl --user link` the templates, add drop-ins for XDG paths and ExecStart, and keep XDG_RUNTIME_DIR short, since a socket path is limited to 108 bytes.

*Observed 2026-10-19 (p2p-network-dev)*
