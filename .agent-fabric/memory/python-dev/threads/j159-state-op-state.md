---
role: "python-dev"
class: threads
topic: "j159-state-op-state"
description: "j159 state op for the interweave-only control plane — PR 640 stacked on #639, review rounds done, what waits"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f75f05372dc03adc
---

## j159 state op for the interweave-only control plane — PR 640 stacked on #639, review rounds done, what waits

j159 (2026-11-17): PR 640 (branch develop-qzapp/python-dev-02/feat/j159-interweave-only-control-plane-the-state), base = python-dev-04's #639 branch (j141, carrier_cfg names). 5 work + 3 fix commits, head 76218685. Three blind review rounds posted (round 1: P1 pool-claim on the inbox thread, P2 state table; round 2 and 3: P3 only). Delivery REPLY sent to the owner (01a1e8f6).

Contract agreed by the owner (REPLY 01a1e82f): record `state-record.json` 0600 atomic, public op `state` {address, state|None, why}, readers ask over control_link Leg under the second carrier alone, relay/dual unchanged, `FABRIC_STATE_READ=op` forces the op under any carrier, `--follow` re-asks every 5 s; ADR-029 op row is the coordinator's.

**Why:** a stacked PR armed now would merge into #639's branch, not main; arm only after #639 merges and the PR retargets.
**How to apply:** after #639 merges: `git fetch`, check the PR base is main and the gate (`fabric-pr gate 640`), re-review the head if a rebase changed it, `fabric-pr arm --basis "<line>"`. Traps: a reply to an op asked over the carrier arrives on the inbox thread, so an op that asks must run beside the loop (`beside_loop`); `post-review` is the bare command with `< file`; `fabric-review next` needs `save` of the previous round first and the derived req-rrN.json for the next one; lint's project-name rule forbids the carrier's name in generic files (use carrier_cfg.SECOND_ONLY); `git commit` and `$HOME` never in one command.

Left: arm after #639 merges; tell fabric-coordinator it merged (ADR-029 row, commands.json/SKILL/completion for the `state` verb); owner's live read-back under dual with FABRIC_STATE_READ=op; j160 (python-dev-03's W1 read-back: report my ledger lines for message 01a1e879) is queued; #639's job-state test flaked once under load.

*Observed 2026-11-17 (python-dev)*
