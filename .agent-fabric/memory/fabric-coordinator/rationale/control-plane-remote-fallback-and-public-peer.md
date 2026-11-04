---
role: "fabric-coordinator"
class: rationale
topic: "control-plane-remote-fallback-and-public-peer"
description: "owner 2026-10-27: a remote host's control fallback is break-glass SSH (hostexec to bin/fabric-op) for now; later an InterWeave peer on a public address so InterWeave works from everywhere (j422 Q6)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 656cb474e6c9d4a0
---

## owner 2026-10-27: a remote host's control fallback is break-glass SSH (hostexec to bin/fabric-op) for now; later an InterWeave peer on a public address so InterWeave works from everywhere (j422 Q6)

The owner answered j422's Q6 on 2026-10-27: "option a for now". When InterWeave is down, a remote host (H2, first edge-hosting) is controlled by break-glass hostexec over SSH to `bin/fabric-op` (j422 gap F3), which checks the same signed operator request. The relay is not exposed on the overlay. The next step the owner named is an InterWeave peer on a public address, so InterWeave works from everywhere, which goes beyond the private overlay with static addresses that the j422 design assumes.

Also on 2026-10-27, in architect-cto's session: "accept the 5b limits but remember me about this after we have the second host". InterWeave ADR-0055 amendment (iii) accepts the two-namespace case's limits for the first remote host: one kernel, no NAT, no second uid, no real second host in CI. ADR-0034 §7 and SPIKE-004 are unchanged. The ADR-064 second-host amendment cites that amendment. Job j440 holds the reminder: tell the owner once the second host runs.

**Why:** the owner wants agents reachable from any host, not only over a private overlay. SSH covers the gap until InterWeave has a publicly reachable peer.

**How to apply:** F3 (`bin/fabric-op` plus the hostexec path) is unblocked. Write the second-host amendment with the SSH fallback. Treat the public peer as the next milestone after H2 (ADR-064 rule 1 lets each milestone open by its own amendment), and expect InterWeave's ADR-0034 §7 and SPIKE-004 limits (discovery, NAT, a public listener) to apply to that step, so ask architect-cto when it comes up. Related: [[control-plane-interweave-for-remote-hosts]].

**State 2026-10-28 (j430):** F3's contract went to python-dev-04 (REQUEST 01a18291-4b8b), chosen because python-dev-03 and -04 had no open jobs. The contract has five rules. (1) fabric-op decides with agentd.accept() itself and shares the account's ActionLedger (actions-seen.json), so a request accepted by either agentd or fabric-op is a replay on the other path. The ledger's record() needs a lock, because two writers now run as the same account. (2) Only ACTION_OPS are accepted, `to` must name the account explicitly (never "*"), and the argv op must match the request's op. (3) The operator side is `fabric-ctl ... --via hostexec`. (4) hostexec keeps no audit log of its own (tools/fabric/hostexec.py), so ADR-010's "a journal line on both hosts" becomes an append-only fabric-op.jsonl on each side, written before the run and refusing the run when that write fails. (5) The ADR-029 amendment that names fabric-op is mine, supplied as a commit onto their branch. It is not in commands.json: a session is never told to run fabric-op.

**State 2026-10-30 (j431):** parked, not started. Its trigger is H2 running, and the owner said that day that H2 does not exist yet (future Proxmox, [[j422-owner-answers-q1-q7]]). j431 is blocked on job:user/j422, which waits on H2, so it wakes with j422 and j440. Nothing went to architect-cto: an early ask about §7/SPIKE-004 would be answered against a host nobody has named.

*References: control-plane-interweave-for-remote-hosts, j422-owner-answers-q1-q7*

*Observed 2026-10-27 (fabric-coordinator)*
