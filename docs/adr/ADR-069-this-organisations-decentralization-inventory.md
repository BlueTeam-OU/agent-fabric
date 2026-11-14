# ADR-069 — This organisation's decentralization inventory

**Date:** 2026-11-12
**Status:** Accepted
**Ratified:** owner, 2026-11-11, the answer to the classification's question (docs/split/move-plan.md §5, ADR-045 A 2026-11-11): the records are split, and ADR-034's own ratification, owner, 2026-09-29, "Accept", carries to the rule and the table moved here
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the inventory of what this organisation's fabric depends on today (one host, one relay, one key, one service) and the duty to keep it current; the criterion it is measured against stays in ADR-034
**Pillar:** P5
**Class:** organisational

## 1. Context and Problem

ADR-034 set P5's criterion for deciding what to decentralize and carried, in its own §1, the table of what one organisation's deployment depends on, with the rule that kept the table current. The table is one deployment's facts: its host, its sixteen logins, its relay and that relay's Proton Drive copy, its observer login. The criterion and its rules hold for any deployment that runs the engine, so the engine's record keeps the number and the criterion, and the table and the duty on it moved here when ADR-034 was split under ADR-045 §5 rule 4. The text of the table is ADR-034's, unchanged but for citations of ADR-034 §7 where the table said §7.

The host has failed twice (`docs/live-checks/2026-09-19-develop-qzapp-crash.md`, `docs/live-checks/2026-09-25-develop-qzapp-crash.md`); ADR-034 §1 tells it.

What depends on one thing, read from the tree:

| what | depends on | if it fails | degraded mode today |
|---|---|---|---|
| every account | one host: `runtime/hosts/registry.json` names one host, `develop-qzapp`, and places all sixteen logins on it | every session and control agent stops; `/home` persists, so identity, bindings and unpushed work survive a reboot of that host, not its loss | none documented beyond the reboot (the Qubes account snapshot, ADR-029 §5 rule 11) |
| messages between sessions | one relay process on the operator's account, loopback only, one SQLite database (ADR-033) | no session receives anything; the channel's past is copied to Proton Drive, encrypted and signed, on a timer scheduled every 6 h, and a restore was read back (`docs/live-checks/2026-10-27-relay-backup-restore.md`); while the timer's runs succeed, a loss takes the messages since the last good copy (6 h, up to 15 min of delay and the run's time; a failed run is only in the journal) | the human relay (ADR-033 §5 rule 7) |
| the control plane | the same relay, channel `fabric:control` (ADR-029) | no account answers; with the relay up and the control agents down, presence reads as unknown and `gzcoord-send` refuses without `--force` (ADR-030) | sudo fallbacks: `bin/fabric-usage`, `bin/fabric-host <host> drain` (ADR-029) |
| signed actions | one key, in the operator's own store (`FABRIC_CONTROL_SIGNING_KEY`) | no upgrade, distribution or account move can be ordered | `fabric-ctl keygen --force` makes a new key; the registry commit carries the public half |
| secrets | each login's own store, a private GitHub repository (ADR-038) | no sync, no rotation, no account move; the tools read the file the last sync wrote, which a failed read does not change | none needed while nothing must change |
| the usage windows | one observer login's sign-ins (ADR-031) | the windows are unread | none |
| model inference | two providers, `anthropic` and `openrouter` (`routing/capabilities.json`); on the plain path, the Claude accounts the templates name (ADR-031) | one path lost reduces capacity; a login is moved to another account by `fabric-accounts assign` or launched on the other provider | routing by capability class (ADR-005) |
| knowledge | git: the fabric's corpus and each project's `.agent-fabric/` on GitHub and in every clone (ADR-013) | an unreachable GitHub stops pushes and merges, not reading | every clone is a full copy |
| an agent's undrained memory | its own home on the host until a drain (ADR-013); copied daily into the login's own store (`agent-fabric-state-backup.timer`, j179), which its parent's backup carries to Proton Drive | a loss of the host takes what was written since the last good daily copy, if a restore works, and no restore has been read back; until a drain no other agent reads it | none documented: the restore is unread, and a drain is collected and landed by hand (ADR-034 §7 step 3 decides its timer) |
| InterWeave between hosts | the provider's DNAT and WAN rule on 195.69.140.18 in front of `fabric-h2` (rule 2), once a roster row names that host | develop-qzapp's profiles cannot dial fabric-h2's accounts; fabric-h2's own accounts still reach each other over loopback | the relay, while it is the transport of record (ADR-064 §5 rule 11) |
| direction and acceptance | the owner (ADR-001 §5 rule 2, ADR-019) | no record is accepted, no PR below the band is armed | none, and this is the point of P3's mandate, not of this record |

## 2. Decision

This organisation keeps the inventory above as this record's §1, and measures every row against ADR-034's criterion: what the failure takes, and the degraded mode, or "none", said plainly. ADR-034 §2 and §5 rules 2 to 5 bind each row; this record adds only the table and the duty to keep it.

## 3. Alternatives Considered

- **Keep the table in ADR-034.** It was the record's rule 1; but a table of one organisation's host and accounts in the engine's record is what ADR-045 moves out.
- **Keep the table in a document that is not a record.** Rejected: a change that adds a dependency amends a record in the same pull request (rule 1), which needs the amendment trail.

## 4. Rationale

The criterion makes the direction testable for any deployment; the inventory is how one organisation tests itself against it. Keeping them in two records lets the engine be published with the criterion while the table, which changes whenever a host, a relay or a key changes, is the operator's to amend.

## 5. Binding Rules

1. The §1 inventory is kept current: a change that adds, removes or moves a dependency an operation relies on amends this record's table in the same pull request.
2. This organisation's second host for GZCoord over InterWeave (ADR-064
   §5 rule 1) is `fabric-h2`, a VM on the Proxmox node s13337. Its ssh
   is reached from develop-qzapp directly over the LAN and its VPN
   (ADR-048). Its InterWeave range is reached at the public address
   195.69.140.18 (A 2026-11-14), which the provider's OPNsense forwards
   to 192.168.200.79 on the same ports, TCP 47100-47199, from any
   source: develop-qzapp is the owner's laptop and travels, so it has
   no fixed address to admit. The owner accepted that this
   puts InterWeave's handshake and parser within reach of the internet
   before InterWeave ADR-0034 §7's release gate (its Stage 18
   adversarial gate) has closed on the pinned release, as a known limit
   for fabric-h2 over the whole range; admission is the roster's PeerIds.
   No roster row names fabric-h2 until a probe from develop-qzapp has
   read the forward back. For its first
   account, a throwaway login for the two-host check, the owner waived
   ADR-034 §7 step 3's held bound and the control parity report; an agent
   moves there only on the owner's word on that report.

## 6. Consequences

- The inventory is a maintenance cost on every change that touches hosts, the relay, keys or services, paid in this record and not in ADR-034.
- A degraded mode is listed only with the live check that read it back (ADR-034 §5 rule 3); the rows that say "none documented" wait on one.

## 7. Future Evolution

The rows change as ADR-034 §7's steps land (the scheduled drain, a second host). The second host reopens ADR-029 §7 and ADR-033 §7 and adds rows here.

## 8. Decision Status

Accepted and in force.

## References

- ADR-034 — the criterion, §5 rules 2 to 5 and §7; the record this one was split from.
- ADR-045 §5 rule 4 — a mixed record is split.
- ADR-029 (the control plane), ADR-030 (presence), ADR-031 (Claude accounts), ADR-033 (the relay), ADR-038 (secrets), ADR-013 (memory and the drain), ADR-005 (routing).
- `runtime/hosts/registry.json`, `routing/capabilities.json`.
- `docs/live-checks/2026-10-27-relay-backup-restore.md`.

## Amendments

The body above reads current; each change's full note is in [history/ADR-069-amendments.md](history/ADR-069-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-11-14 | fabric-h2's InterWeave range is a public forward from any source | §1 a row for InterWeave between hosts; §5 rule 2: the address, the forward and the owner's acceptance of the exposure |
