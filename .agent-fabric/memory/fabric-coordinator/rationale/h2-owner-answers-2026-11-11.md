---
role: "fabric-coordinator"
class: rationale
topic: "h2-owner-answers-2026-11-11"
description: "Owner's three answers for H2 (j706), 2026-11-11: install done, no overlay (direct over LAN/VPN), both P2 gates waived"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e6c707ab1666d2d3
---

## Owner's three answers for H2 (j706), 2026-11-11: install done, no overlay (direct over LAN/VPN), both P2 gates waived

The owner answered in my session on 2026-11-11, for j706 (H2, fabric-h2 = VM 101 on s13337):

1. **The console install is done.** That is AlmaLinux 10 x86_64_v2 with hostname fabric-h2, user `op` holding the operator's key, and qemu-guest-agent. The next step is for devex-tooling (j320) to read the address from the guest agent.
2. **Overlay: none. develop-qzapp reaches fabric-h2 directly over the LAN or VPN.** This replaces the WireGuard plan in j422 §3.1. The registry's `ssh` and `interweave_address` fields take the LAN address. The firewall boundary (47100-47199 admitted only from the peer) still has to be stated in the ADR-048 and ADR-064 amendments.
3. **Gates are waived for P2**, meaning registration plus the throwaway-login two-host check:
   - ADR-034 §7 step 3's held bound. The drain is built and recorded on #551, but the bound is only reported.
   - P1's control parity report.
   P3 (moving edge-hosting) still waits for the parity report.

**Why:** architect-cto's REQUEST 01a1c063 said the gate waiver is the owner's to give, never to be inferred.
**How to apply:** cite this as the owner's word in the ADR-064 amendment, and as "accepted on the owner's word" in the §2 gate text. Related: [[h2-is-a-vm-on-s13337]], [[j422-owner-answers-q1-q7]].

**Landed on the j706 branch** (377c3880, pushed 2026-11-11, no PR yet: it waits on #551 because one PR is open at a time). It has 5 work commits: the schema's almalinux; the entry `fabric-h2` (op@a private-network address, sshd keys pinned) and live check `docs/live-checks/2026-11-11-fabric-h2-registered.md`; ADR-064 rule 1; ADR-048 rules 1 and 8; ADR-010 §7.

The key reached op by the owner's `ssh-copy-id` with op's password. qemu-ga on EL disables guest-exec/file-*, so devex-tooling could not do it. Out-of-band pin: the keys were read on the host and `fabric-ssh-hosts check` ran there.

The way back is closed: fabric-h2 cannot reach develop-qzapp (it sees develop-qzapp as a private-network address), and I told architect-cto this. op's sudo asks for a password, and the owner decides next. Open jobs: j762 (python3 3.12 against the 3.13 floor) and j763 (almalinux CI leg after #554). #554 waits on the owner's arm word.

To run hostexec against the branch registry: `AGENT_FABRIC_HOSTS_REGISTRY=$PWD/runtime/hosts/registry.json ./bin/fabric-host fabric-h2 check`. `AGENT_FABRIC_ROOT` does not reach hostexec.

The owner, 2026-11-11: "arm both when possible", meaning #554 (python-dev-02's; word relayed, REPLY 01a1c9a8) and my #551. It counts once a PR's CI is green and its review gate passes. A head that moves still needs the gate, not a new word.

*References: h2-is-a-vm-on-s13337, j422-owner-answers-q1-q7*

*Observed 2026-11-11 (fabric-coordinator)*
