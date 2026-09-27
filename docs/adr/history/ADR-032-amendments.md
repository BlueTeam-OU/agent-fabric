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
