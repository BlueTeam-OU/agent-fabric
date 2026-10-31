---
role: "fabric-coordinator"
class: rationale
topic: "j422-owner-answers-q1-q7"
description: "owner 2026-10-30 on j422 §10: ADR-034 order wins, H2 is a future Proxmox server (gzapp production too), overlay and VM/container deferred, the agent moves with its key, control moves to InterWeave now"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 06daf626cd30216f
---

## owner 2026-10-30 on j422 §10: ADR-034 order wins, H2 is a future Proxmox server (gzapp production too), overlay and VM/container deferred, the agent moves with its key, control moves to InterWeave now

The owner answered the open questions in docs/proposals/j422-control-plane-on-interweave-cli.md §10 on 2026-10-30:

- **Q1:** ADR-034's order wins. The relay-loss rows (j433, the drill) and the scheduled drain (j434) land before any second host.
- **Q2:** H2 does not exist yet. It will be a Proxmox server that also runs gzapp in production, plus "other selected things".
- **Q3:** the overlay (WireGuard by hand or a mesh) is decided once the infrastructure exists.
- **Q4:** "an agent simply moves from the current host to run there". The agent keeps its operating model; it does not become a new operator seat. Whether it runs in a Proxmox VM or in a container inside an agents-only VM is decided later. Confirmed by the owner the same day: H2 has no operator signer, and fabric-ctl stays on develop-qzapp.
- **Q5:** "move means move". The keyring and the ADR-038 subkey are carried over and not rotated. This reverses the plan's proposed rotation.
- **Q6** (restated): if InterWeave is down, the fallback is SSH for now.
- **Q7:** move now, without waiting for InterWeave ADR-0064.

**Why:** the owner wants the second host to be production infrastructure (Proxmox), not a dedicated agent box. The move keeps the agent's identity whole.

**How to apply:** do not draft the ADR-064 second-host amendment until the Proxmox server exists and j433 and j434 have landed. When drafting it, write §3.4's subkey step as carry-over instead of rotation, put the VM/container placement and the overlay to the owner, and keep the plan's P0/P1 (dual run on develop-qzapp) going now, because Q7 is "move now". Related: [[control-plane-interweave-for-remote-hosts]], [[control-plane-remote-fallback-and-public-peer]].

*References: control-plane-interweave-for-remote-hosts, control-plane-remote-fallback-and-public-peer*

*Observed 2026-10-30 (fabric-coordinator)*
