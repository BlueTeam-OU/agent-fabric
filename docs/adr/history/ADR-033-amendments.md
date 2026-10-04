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
