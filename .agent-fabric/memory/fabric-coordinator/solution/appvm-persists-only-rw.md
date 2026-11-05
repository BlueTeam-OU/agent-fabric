---
role: "fabric-coordinator"
class: solution
topic: "appvm-persists-only-rw"
description: "develop-qzapp is a Qubes AppVM (rw-only): a sysctl or /etc change is lost at reboot; persist root settings under /rw/config/rc.local.d"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 28abe754cd43f581
  - d3c0436f32ddecfe
---

## develop-qzapp is a Qubes AppVM (rw-only): a sysctl or /etc change is lost at reboot; persist root settings under /rw/config/rc.local.d

develop-qzapp: `qubesdb-read /qubes-vm-persistence` = rw-only, type AppVM. Only /rw (and /home, /usr/local) survive a reboot; /etc comes from the template. net.ipv4.ip_local_reserved_ports=47100-47199 (ADR-064 rule 1), set by hand 2026-10-26, was empty after the 2026-10-30 05:08Z reboot; boot-enabled InterWeave units came up anyway (systemd does not check it), but `fabric-ctl all interweave-start` refused all 30 accounts. Persisted 2026-10-30 by the owner as /rw/config/rc.local.d/agent-fabric-interweave.rc.

**How to apply:** any host setting provisioning needs on this host goes to /rw/config/rc.local.d/<name>.rc, never /etc/sysctl.d. For the reserved ports provisioning owns it now: `fabric-host <host> persist` (#449, persist_host_settings.py) generated agent-fabric-interweave.rc on 2026-11-01, replacing the owner's hand copy (live check docs/live-checks/2026-11-01-reserved-ports-persist.md, ADR-064 A 2026-11-01 on #456). After the next reboot read `fabric-ctl all interweave` reserved_ports before any interweave-start. Related: [[cpu-lease-counts-runs-and-threads]].

*References: cpu-lease-counts-runs-and-threads*

*Anchors: `tools/fabric/control/carrier_install.py::RESERVED_PORTS_HINT`*

*Observed 2026-11-01 (fabric-coordinator)*
