---
role: "fabric-coordinator"
class: rationale
topic: "h2-is-a-vm-on-s13337"
description: "Where the second host H2 is: an AlmaLinux 10 VM on Proxmox node s13337, made through the PVE API by the agent that holds the credential, never the node itself"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a5026a6d9246c5bd
---

## Where the second host H2 is: an AlmaLinux 10 VM on Proxmox node s13337, made through the PVE API by the agent that holds the credential, never the node itself

Owner, 2026-11-09: s13337 (a private-network address) is a Proxmox VE node that also runs gzapp in production. It is not H2. H2, the host of the j422 plan (`docs/proposals/j422-control-plane-on-interweave-cli.md` §3), is a VM for agents on it.

- **Who creates it:** through the PVE API only. Nobody, the owner included, has ssh to the node. The owner says an API credential already exists in devex-tooling's or edge-hosting's store. A credential never moves between stores, so its holder creates the VM, on a contract I write. Asked both by QUESTION on 2026-11-09 (01a1c18e-66d5, 01a1c18e-6f00). My pveum token script was dropped: it needed root on the node.
- **OS:** AlmaLinux 10. This is the owner's answer, not one of my two options (Fedora, Debian). bootstrap and the tool proofs have never run on an EL distribution, so expect porting findings.
- The registry's `hosts.H2` entry names the VM, not a private-network address. This replaces architect-cto's request to place edge-hosting "on s13337" (01a1c187, j715; j706).

**Why:** the plan's H2 needs its own account set, linger and its own failure domain. The node itself carries production.
**How to apply:** the decision needs a record (ADR-064 second-host amendment, ADR-048) before the entry lands. Related: [[control-plane-remote-fallback-and-public-peer]], [[own-secrets]].

2026-11-09 18:26Z answers: edge-hosting holds none. devex-tooling holds `PROXMOX_API_TOKEN`, which is the bare UUID secret with no `user@realm!tokenid`, so it is unusable alone. It also printed the value in its own transcript (exposed, so it must be rotated). Next: the owner rotates it in the PVE UI and tells me the token id, then the new value goes in as the `PVEAPIToken=` form.

18:31Z: the owner gave devex-tooling the id directly, so the token is `cld9-012544@pve!fabric`. It is kept, not rotated. TLS: the node presents only its leaf, issued by its own PVE CA, and curl fails with exit 60. Leaf sha256 23:EF:DC:A4:…:9B:9B:5B, pubkey pin `sha256//MIdho6lH9PCso/r9R7ZmLUMzjW9xkVVMKCGb5O7H9qs=`. `curl -k --pinnedpubkey` works (401 unauthenticated). The pin is trust-on-first-use until the owner confirms the fingerprint in the PVE UI.

18:40Z owner: the VM is on vmbr2 (OPNsense LAN), 2 vCPU, 8 GiB, 100 GiB on local-lvm. The image is blocked: neither the token nor the owner may upload. The owner asked the provider for the right, or for the provider to place the ISO. devex-tooling read the token (18:36Z, 01a1c199): VM.* on /vms, AllocateSpace on local and local-lvm, SDN.Use, no AllocateTemplate. Paused until the provider answers; back to the fabric work meanwhile.

2026-11-10 ~20:40Z: devex-tooling's j320 created VM 101 `fabric-h2` (MAC BC:24:11:BA:13:FA, vmbr2) from the AlmaLinux 10 ISO; start failed, the node's KVM CPU lacks x86-64-v3 (EL10's baseline). Owner chose AlmaLinux 10's x86_64_v2 build (cpu x86-64-v2-AES), and says the token now has AllocateTemplate, so devex-tooling places the ISO itself (REPLY to 01a1c731). The node is a private-network address: a probe of a private-network address times out and reads as "unreachable".

*References: control-plane-remote-fallback-and-public-peer, own-secrets*

*Observed 2026-11-10 (fabric-coordinator)*
