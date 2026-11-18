---
role: "edge-hosting"
class: solution
topic: "s13337-is-gzapp-prod-node"
description: s13337 is the Proxmox node running gzapp production; no agent runs on it — agent stage hosts are VMs on it (H2, AlmaLinux 10)
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1aa36f6055dcac54
---

## s13337 is the Proxmox node running gzapp production; no agent runs on it — agent stage hosts are VMs on it (H2, AlmaLinux 10)

s13337 is the Proxmox node that runs gzapp production; no agent login is placed
on it. A request that says "deploy on s13337" means a VM on that node: on
2026-11-09 the owner's word (via fabric-coordinator) made H2, an AlmaLinux 10 VM
fabric-coordinator creates there, the stage host for the InterWeave daemon +
Claude bridge (my j27). Its address comes from runtime/hosts/registry.json once
the placement lands, and nothing starts before fabric-coordinator says the login
on H2 is ready.

**Why:** architect-cto-01's first request named s13337 itself and was corrected
the same day; acting on the node would have put an agent beside production.

**How to apply:** read "s13337" in a task as "a VM on s13337" and check the
registry for which one. H2 shares the node (hardware, hypervisor, its network
path) with gzapp production, so anything claimed independent of gzapp — a status
surface, a recovery path — cannot live on H2 ([[gzapp-status-hostnames-2026-10-19]]).
On EL10, check the user manager, linger under polkit and SELinux on units
running binaries from ~ before following a Fedora-recorded procedure.

*References: gzapp-status-hostnames-2026-10-19*

*Anchors: `interweave:packaging/linux/DEPLOYING.md::glibc 2.35 or later`*

*Observed 2026-11-09 (edge-hosting)*
