# ADR-034 — Decentralization as a direction: a failure may reduce capacity, never take identity, knowledge or continuity

**Date:** 2026-09-27
**Status:** Accepted
**Ratified:** owner, 2026-09-29, "Accept", answering fabric-coordinator's question closing the Proposed records; carried by the pull request that marks them Accepted
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the criterion by which the fabric decides what to decentralize, and the inventory of what depends on one host, one relay, one key or one service today; a direction the fabric's changes are argued against
**Pillar:** P5

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

What depends on one thing today, read from the tree:

| what | depends on | if it fails | degraded mode today |
|---|---|---|---|
| every account | one host: `runtime/hosts/registry.json` names one host, `develop-qzapp`, and places all sixteen logins on it | every session and control agent stops; `/home` persists, so identity, bindings and unpushed work survive a reboot of that host, not its loss | none documented beyond the reboot (the Qubes account snapshot, ADR-029 §5 rule 11) |
| messages between sessions | one relay process on the operator's account, loopback only, one SQLite database (ADR-033) | no session receives anything; the channel's past is only in that database | the human relay (ADR-033 §5 rule 7) |
| the control plane | the same relay, channel `fabric:control` (ADR-029) | no account answers; with the relay up and the control agents down, presence reads as unknown and `send.mjs` refuses without `--force` (ADR-030) | sudo fallbacks: `bin/fabric-usage`, `bin/fabric-host <host> drain` (ADR-029) |
| signed actions | one key, in the operator's own store (`FABRIC_CONTROL_SIGNING_KEY`) (A 2026-09-30) | no upgrade, distribution or account move can be ordered | `fabric-ctl keygen --force` makes a new key; the registry commit carries the public half |
| secrets | each login's own store, a private GitHub repository (ADR-038) (A 2026-09-30) | no sync, no rotation, no account move; the tools read the file the last sync wrote, which a failed read does not change | none needed while nothing must change |
| the usage windows | one observer login's sign-ins (ADR-031) | the windows are unread | none |
| model inference | two providers, `anthropic` and `openrouter` (`routing/capabilities.json`); on the plain path, the Claude accounts the templates name (ADR-031) | one path lost reduces capacity; a login is moved to another account by `fabric-accounts assign` or launched on the other provider | routing by capability class (ADR-005) |
| knowledge | git: the fabric's corpus and each project's `.agent-fabric/` on GitHub and in every clone (ADR-013) | an unreachable GitHub stops pushes and merges, not reading | every clone is a full copy |
| an agent's undrained memory | its own home on the host, until a drain (ADR-013) | lost with the host | none: a drain is run by hand |
| direction and acceptance | the owner (ADR-001 §5 rule 2, ADR-019) | no record is accepted, no PR below the band is armed | none, and this is the point of P3's mandate, not of this record |

## 2. Decision

**Decentralize only where a failure would otherwise take
identity, knowledge or the ability to go on working — and measure every
piece against that criterion, not against a topology.** Reduced capacity
is acceptable; loss is not. A component that is central but whose
failure only slows the team (the usage observer) stays central; one whose
failure loses what cannot be rebuilt (the relay's database as the only
record of the channel, an agent's undrained memory on one host) gets a
second copy or a documented recovery before it gets a second instance.

- Every operation the fleet depends on has a row in this record's §1
  inventory: what it depends on, what its failure costs, and its degraded
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
  has already failed twice, and two rows (the relay's database, undrained
  memory) lose data on a loss of the host rather than a reboot.
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

1. The §1 inventory is kept current: a change that adds, removes or moves
   a dependency an operation relies on amends this record's table in the
   same pull request.
2. A dependency whose failure loses data that exists nowhere else gets a
   second copy or a documented, read-back recovery before any other work
   on its row.
3. A degraded mode is listed only with the live check that read it back;
   until then the row says "none documented".
4. Identity stays derivable without any central service: the login and
   the host (ADR-002). No design makes an agent's identity depend on the
   relay or GitHub being reachable (A 2026-09-30).
5. A proposal to decentralize a component states which row it changes and
   what failure it stops from taking identity, knowledge or continuity;
   one that changes only capacity says so and competes with other
   capacity work.

## 6. Consequences

- The inventory is a maintenance cost on every change that touches
  hosts, the relay, keys or services.
- Two rows lose data today on a loss of the host: the relay's database
  and every agent's undrained memory. Nothing backs up the first; the
  second is copied only when a coordinator runs a drain.
- The degraded modes listed today are unverified by this
  rule until each has its live check; the human relay's was exercised in
  practice before the relay existed, not as a drill.

## 7. Future Evolution

**The first concrete step:** a copy of the relay's database off its
database file — on a schedule, to a location the host's loss does not
take — and a restore read back as a live check: the relay started on the
copy, `fabric-ctl all ping` answered, and a session's `gzcoord-inbox
--replay` showing the channel's past. **What would show it worked:** the
relay row's "if it fails" no longer says the channel's past is lost, and
the live check exists.

After it: a drill of the relay being down for a working hour — sessions
continue from artifacts, what must go goes by the human relay, nothing is
lost — read back as a live check; a scheduled drain, so undrained
memory is bounded in age; and only then the second host, which reopens
ADR-029 §7 and ADR-033 §7.

## 8. Decision Status

Accepted and in force.

## References

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
