# ADR-033 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-30 — Doppler is retired: the store holds what Doppler held

Doppler is removed from the fabric (ADR-038, agent-fabric #69): every
account reads its own store, and the coordinator's templates and
signing key live in the coordinator's store. Rule 6: the relay token comes from the
account's own store.

### Amendment 2026-10-04 — cccc recorded as a refused alternative

The owner refused cccc (github.com/ChesterRa/cccc) as the GZCoord
transport on 2026-09-15. The refusal and its reasons lived only in
gzapp's architect-cto rationale slice
`gzcoord-transport-why-not-cccc`, distilled 2026-09-28, while the
transport is the fabric's subject. architect-cto-01 asked for the
row in its rationale staging pass (message
01a10636-a49d-7faa-8c86-9ebcbc284886); the gzapp slice is deleted at
the next drain. Nothing about the decision changes: §3 gains the
alternative the owner had already refused, with the reasons the slice
gave.

### Amendment 2026-10-13 — a persona marked as AI is not a human-style identity (ADR-056)

Rule 3's reason is an agent "appearing to be" a person. ADR-056 gives
agents personas — a first name, a scientist's surname, an illustrated
avatar — always behind the prefix "AI", so a persona discloses what it
is; rule 3 now says so, and still forbids any identity that passes for a
person. The owner's words, in the coordinator's session: "only we should
keep ai agent clearly identificable as such".

### Amendment 2026-10-28 — A second host is reached over InterWeave, not by the relay

What changed: §7's first two bullets were stale. A second host is
reached over InterWeave (ADR-064 rule 1's next milestone), not by a
relay URL; InterWeave already carries GZCOORD/1 beside the relay on its
host (ADR-064), and ADR-029 rule 18 adds the control records once
its carrier is built.

Why: the same day's ADR-029 and ADR-064 amendments (agent-fabric j422).

### Amendment 2026-11-18 — The data plane's first gate: an account in `carrier-record` has InterWeave as its record, the relay as its mirror

What changed: §2's third bullet said the relay is the transport, and
§7 that it stays the record until the owner's word. For GZCoord
messages the record now moves account by account, under the mode
ADR-064 §7 names: an account in `carrier-record` has InterWeave as its
transport of record (its send's exit status is the carrier's answer,
its watch waits on the carrier, its replay reads the journal) and the
relay as its mirror both ways, kept whole by the mirror post and the
backfill; an account in `relay-record` is as before. Control stays on
the relay (ADR-029). §8 says the same.

Why: gate 1 of the cutover plan
(`docs/proposals/gzcoord-interweave-only-cutover.md` §4). Its evidence
is filed: #573's real-carrier read-back, the rollback drill
(`docs/live-checks/2026-11-12-interweave-drills.md`), the relay-outage
drill (`docs/live-checks/2026-11-15-relay-outage-drill.md`) and a parity
report with no InterWeave miss over 562 pairs
(`docs/live-checks/2026-11-18-interweave-parity.md`). Rule 7, the human
relay when the relay is down, changes at gate 2, when an account leaves
the relay altogether.

Accepted by the owner, 2026-11-18, in the coordinator's session (gate
1's word). ADR-064 §2, rules 7 and 11 are amended the same day.
