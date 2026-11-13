# ADR-034 — Decentralization as a direction: a failure may reduce capacity, never take identity, knowledge or continuity

**Date:** 2026-09-27
**Status:** Accepted
**Ratified:** owner, 2026-09-29, "Accept", answering fabric-coordinator's question closing the Proposed records; carried by the pull request that marks them Accepted
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the criterion by which the fabric decides what to decentralize, and the duty to keep an inventory of what depends on one host, one relay, one key or one service, which the operator holds in its own record (ADR-069 here); a direction the fabric's changes are argued against
**Pillar:** P5
**Class:** engine

## 1. Context and Problem

ADR-000's P5 direction: "Decentralization where it produces real
autonomy and resilience, not complexity for its own sake. The criterion:
a failure or a change of provider may reduce the team's capacity for a
while; it must not take its identity, its knowledge or its ability to go
on working. Dependence on one person is not replaced by dependence on one
central service. Every operation the organization depends on has a
documented degraded mode." P5's Today states that the GZCoord relay is
central: one process on one host.

The host has failed twice: on 2026-09-19 and on 2026-09-25 `develop-qzapp`
died under load (`docs/live-checks/2026-09-19-develop-qzapp-crash.md`,
`docs/live-checks/2026-09-25-develop-qzapp-crash.md`), and on
2026-09-25 sixteen sessions ended at once. Identity and memory survived
both, because `/home` persists and identity is the login; what stopped
was everything that runs on that host.

What depends on one thing in a deployment, and what each failure takes,
is that deployment's inventory, which its operator keeps in its own
record (ADR-069 here): one host, one relay and its database, one signing
key, one observer, two providers, undrained memory, the owner, each with
its degraded mode or "none".

## 2. Decision

**Decentralize only where a failure would otherwise take
identity, knowledge or the ability to go on working — and measure every
piece against that criterion, not against a topology.** Reduced capacity
is acceptable; loss is not. A component that is central but whose
failure only slows the team (the usage observer) stays central; one whose
failure loses what cannot be rebuilt (the relay's database, before it had a
copy, an agent's undrained memory before it had a daily copy) gets a
second copy or a documented recovery before it gets a second instance.

- Every operation the fleet depends on has a row in the operator's
  inventory (ADR-069 here): what it depends on, what its failure costs, and its degraded
  mode — or "none", said plainly.
- A degraded mode counts only when it has been read back: a live check
  shows the operation continuing, reduced, with the dependency removed.
- No change replaces dependence on one person with dependence on one
  central service; a change that adds a single point for identity,
  knowledge or continuity justifies it in its own §4 (ADR-000 §5 rule 3).

## 3. Alternatives Considered

- **Decentralize everything** — a relay per host, a federation of
  control planes, peer-to-peer delivery. Rejected as a goal: P5 asks for
  autonomy and resilience, not topology; each added instance is state to
  reconcile, and several rows above lose nothing when they fail.
- **Accept centralization and plan only for reboots.** Rejected: the host
  has already failed twice, and two rows lost data on a loss of the host rather than a reboot when this was written (the relay's now has a copy, §7; undrained
  memory has a daily copy whose restore is unread, ADR-069 §1).
- **A second host first.** Deferred, not rejected: it is the largest
  step, it needs a relay the second host can reach (ADR-029 §7), and it
  helps only once the rows that lose data have a copy.

## 4. Rationale

The criterion makes the direction testable. Each row of the inventory
answers one question — what does this failure take? — and the answer
orders the work: first what loses data, then what stops work with no
fallback, last what only reduces capacity. It also keeps the fabric from
building the complexity P5 warns against: a second relay that splits the
record would make the channel less durable, not more.

## 5. Binding Rules

1. The operator keeps its inventory of dependencies in its own record
   (ADR-069 here), and keeps it current: a change that adds, removes or
   moves a dependency an operation relies on amends that record's table in
   the same pull request (A 2026-11-12).
2. A dependency whose failure loses data that exists nowhere else gets a
   second copy or a documented, read-back recovery before any other work
   on its row.
3. A degraded mode is listed only with the live check that read it back;
   until then the row says "none documented".
4. Identity stays derivable without any central service: the login and
   the host (ADR-002). No design makes an agent's identity depend on the
   relay or GitHub being reachable (A 2026-09-30).
5. A proposal to decentralize a component states which row of the inventory it changes and
   what failure it stops from taking identity, knowledge or continuity;
   one that changes only capacity says so and competes with other
   capacity work.

## 6. Consequences

- The operator's inventory is a maintenance cost on every change that touches
  hosts, the relay, keys or services.
- Every agent's undrained memory is copied daily with the login's
  working state (ADR-069 §1), but no restore of that copy has been read back,
  and it reaches no other agent until a drain, which until §7 step 3
  is built runs only by hand. The relay's database is scheduled to be
  copied every 6 h (§7).
- The degraded modes listed today are unverified by this
  rule until each has its live check; the human relay's was exercised in
  practice before the relay existed, not as a drill.

## 7. Future Evolution

**The first concrete step is done:** the relay's database
is scheduled to be copied every 6 h (`agent-fabric-relay-backup.timer`, on the relay's
account) to Proton Drive, encrypted and signed, with `fabric-secrets
relay backup|--verify|restore`. Its restore was read back: a second relay
started on the copy and `gzcoord-inbox --replay` showed the channel's
past (`docs/live-checks/2026-10-27-relay-backup-restore.md`). The
timer's scheduled runs have been read back since; a restore off the
host (it ran on the host that holds the database) is not shown.

**The second step is done:** the relay was down for a working hour
and came back on the restored copy of its
database (`docs/live-checks/2026-11-07-relay-down-drill-hour.md`).
Sessions went on from artifacts (9 commits on origin against 10 in the
hour before); the copy restored whole, seq continued without a gap,
`fabric-ctl all ping` answered from every account through it, and the
five messages the relay shows written during the hour reached it once it
was back; a message never resent is not shown either way.
An operator's stop holds: no watch restarts the relay. The human relay
was not needed in that hour and stays unexercised.

After it: the scheduled drain (step 3, below), so undrained memory is
bounded in age; and only then the second host, which reopens ADR-029 §7 and ADR-033 §7.

**Step 3, the scheduled drain, is decided as follows (j434; built,
(A 2026-11-10)).** The loss of the host is covered by the daily state copy (ADR-069 §1),
so the age this step bounds is how long knowledge waits before every
agent can read it:

- **The bound: 14 days.** No drainable memory (one with a
  `roles_class`) stays older than 14 days outside the corpus — a week
  to the next collection and a week to land it. The age is the
  memory's own time against the store's watermark in the project's
  `last-drain-report.json`, the same mark the harvester reads.
- **Collection is scheduled; landing stays reviewed.** A weekly timer
  on the coordinator's account (`agent-fabric-drain.timer`, Monday
  06:00 UTC, persistent) runs `fabric-ctl all memory`, an unsigned
  read, into the coordinator's state directory, so every account's
  undrained memory is in a verified bundle on the coordinator's
  account within a week whatever its own sessions do. Assembly and
  landing are not scheduled: a collision needs the owner's ruling and a
  drain lands as reviewed pull requests (`memory/README.md`).
- **The report.** Each run writes one report beside its bundles: per
  store, the drainable count and the age of its oldest undrained
  memory against the bound; an account that did not answer is
  *unknown*, never zero. It puts one drain job on the coordinator's
  list, high when a store is over the bound, and updates the open one
  rather than stacking a second. `fabric-status` prints the age of
  the oldest undrained memory beside its count, on every account.
- **Off-role, it does nothing.** The service runs only under a
  `fabric-coordinator` binding and says so otherwise: authority is the
  role's, not the account's.

**Built, and run by its timer (A 2026-11-10).** #419 built the
collection, the report and the job (`bin/fabric-drain-due`), and #462
installs the timer on the coordinator's account. Its first scheduled
run exited 0 and put drain job j689 on the
coordinator's list: of 107 stores, 54 answered, and the 50 with
drainable memory held 833 claims, the oldest 54.5 days against the
bound of 14 and 33 stores over it; 53 stores were *unknown* (34 with no usable harvest report, 19 whose
bundle had no working copy). The bound is reported, not yet held.

Not decided here: issuing the weekly reflection passes (a signed
action, ADR-058) stays by hand; a dry assembly that names collisions
before the job is taken is a later step.

## 8. Decision Status

Accepted and in force.

## References

- ADR-069 — this organisation's inventory, moved out of §1 by the split.
- ADR-000 §5, P5 (Today, Direction) and rule 3.
- ADR-002 (identity), ADR-005 (routing by class), ADR-010 (hosts),
  ADR-012 (credentials), ADR-013 (memory and the drain), ADR-029 (the
  control plane), ADR-030 (presence), ADR-031 (Claude accounts), ADR-033
  (the relay).
- `runtime/hosts/registry.json`, `runtime/control/config.json`,
  `communication/gzcoord/runtime/gzcoord-relay.service`,
  `routing/capabilities.json`.
- `docs/live-checks/2026-09-19-develop-qzapp-crash.md`,
  `docs/live-checks/2026-09-25-develop-qzapp-crash.md`.

## Amendments

The body above reads current; each change's full note is in [history/ADR-034-amendments.md](history/ADR-034-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-30 | Doppler is retired: the stores replace it | §1 table (signed actions, secrets), §5 rule 4 |
| 2026-10-27 | The relay's database is copied off the host: step 1 of §7 done | §1 relay row, §6, §7 first step |
| 2026-10-28 | Undrained memory has a daily copy; §7 step 3, the scheduled drain, decided | §1 memory row, §2, §3, §6, §7 step 3 |
| 2026-11-07 | The relay down for a working hour: step 2 of §7 done | §7 first and second steps |
| 2026-11-10 | Step 3 of §7 built; its first scheduled run read back | §7 step 3 |
| 2026-11-12 | The inventory moves to the operator's record | §1: the inventory table leaves; §2, §3, §5 rules 1 and 5, §6, §7 cite ADR-069; the criterion, rules 2-4 and §7 stay |
