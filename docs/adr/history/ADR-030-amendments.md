# ADR-030 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-27 — HELLO and GOODBYE retired

The owner, to the fabric-coordinator session: "i think it's time to
remove hello and goodbye from gzcoord protocol".

Rule 7 said the two types were deprecated: SHOULD NOT be sent, still
accepted by a conforming parser. Since presence replaced them, nothing
sends either: the launcher no longer does, and the one generator,
`gzmsg.mjs hello`, had no caller outside its own tests. They are retired
inside GZCOORD/1 (agent-fabric ADR-032, amended the same day): a parser
rejects a message of either type and names it as retired. This narrows
the accepted set, which GZCOORD/1 allows (ADR-032 rule 4); an earlier
reader still accepts every message a current sender emits. The inbox
keeps acknowledging one from an old session without delivering it.
