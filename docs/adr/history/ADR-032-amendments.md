# ADR-032 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-27 — HELLO and GOODBYE retired

The owner, to the fabric-coordinator session: "i think it's time to
remove hello and goodbye from gzcoord protocol".

What changed: SPEC §5 says `HELLO` and `GOODBYE` are retired; §8 keeps
its number as the record of why; §10 and §11 drop them; §14's adapter
associates the `FROM` of any observed message with native identity; §18
adds the parser rule that rejects a message of either type, naming it as
retired. MESSAGE-FORMAT, SEMANTICS and CONFORMANCE, the validator, the
inbox, the examples and the tests change in the same pull request (rule
8).

Under which rule: rule 4, a narrowing of the core accepted set within
GZCOORD/1. Every message a sender of this text emits was already valid
under every earlier GZCOORD/1 text; a reader of an earlier text still
accepts it. No grammar changes (rule 3).

The evidence of rule 6: presence replaced the announcements (ADR-030),
the launcher stopped sending them, and the only generator
(`gzmsg.mjs hello`) had no caller outside its own tests; the inbox had
already stopped delivering either type. An old session that still sends
one is acknowledged without delivery.

### Amendment 2026-09-28 — The retirement's loose ends

What the retirement of `HELLO` and `GOODBYE` left behind (review of
agent-fabric #55, carried to the next pull request on the owner's rule
that a P3 may wait).

SPEC.md's header read `Status: Draft`; §6 of this record said it would
change with the first amendment, and the first amendment did not change
it. It now reads `Status: Normative` and names this record. §1 no
longer lists "self-description and discovery" among what the protocol
standardizes, and §4 no longer says instances "announce" a role. §9
defined `CAPABILITIES` for a message type that no longer exists; it and
`SPECIALTIES` are optional metadata any message may carry, which the
validator already knew as common keys and a parser preserves (§6). The
gzcoord README and the runtime README say the same.

Under which rule: rule 4 — nothing a sender emits becomes invalid; the
two fields were already preserved as unknown metadata by every reader.
