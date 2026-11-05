---
role: "fabric-coordinator"
class: solution
topic: "reserved-ports-readback-verb"
description: "how to read back ADR-064's reserved ports after a reboot — the verb takes no argument, and the column needs restarted control agents"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 313b7f09e5f2fb7e
---

## how to read back ADR-064's reserved ports after a reboot — the verb takes no argument, and the column needs restarted control agents

The read-back of the reserved ports (#456, merged 2026-11-03 as 09910b5c) is
`fabric-ctl <login|all> interweave`, with no argument after it. Run as
`fabric-ctl all interweave reserved_ports`, it failed with "all is not a placed
account". The `reserved_ports` field is in that report only once each account's
control agent runs the merged code. Right after `fabric-ctl all upgrade fabric`
the old agents answered without it. To check the host directly:
`cat /proc/sys/net/ipv4/ip_local_reserved_ports` (47100-47199) and
`/rw/config/rc.local.d/agent-fabric-interweave.rc`, which
`persist_host_settings.py` installs (it runs from `fabric-host <host> persist`).

*Anchors: `tools/fabric/provisioning/persist_host_settings.py::net.ipv4.ip_local_reserved_ports`, `runtime/provisioning/platform/README.md::agent-fabric-interweave.rc`*

*Observed 2026-11-03 (fabric-coordinator)*
