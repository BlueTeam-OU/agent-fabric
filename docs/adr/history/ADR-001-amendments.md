# ADR-001 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-27 — A source is refused whatever the trailer

Rule 9 said `adr.py range-check` refuses an edit to a source "without an
`ADR-Editorial:` trailer", which is what the code did: the trailer skipped
the whole commit, so a source could be edited, or deleted, under it and
CI stayed green. A review thread on agent-fabric #51 reproduced the
deletion. The code now applies the trailer to a record's body edit only
and refuses any edit, rename or removal of a source whatever the
message says, with a test for each; the rule says the same. The rule's
first sentence — a source is never edited — is unchanged; its
enforcement now matches it.

### Amendment 2026-09-27 — No inline attributions

The owner, 2026-09-27, to the fabric-coordinator session: remove this
kind of thing from any ADR — "(the owner, 2026-09-13)".

Records carried parenthetical attributions after their decisions — 36 of
them across ADR-001 to ADR-026 and the DIGEST, most in the form "(the
owner, YYYY-MM-DD)", a habit carried over from the notes they replaced.
They are removed: the six that described something rather than
attributing it are reworded, and a date that belonged to the content
stays in the sentence. Rule 10 states the rule, and `adr.py check` now
refuses a parenthesis in a record's body (between the header and the
Amendments table) or in the DIGEST that opens on "the owner" or "the
CEO", across a line break too. The header, the history notes and
`sources/` keep their provenance: that is where it belongs.

### Amendment 2026-09-27 — A record reads current

The owner, 2026-09-27, to the fabric-coordinator session, on the rule
added the same day that a date belonging to the content stays in the
sentence: "not sure also this is necessary"; asked how far dates should
go, the owner chose to keep them only in §1.

The records carried 140 dates in §2 to §8: "since …" before a rule,
"Accepted since …" in §8 repeating the header, "rejected on …" in §3.
They are removed; each sentence is rewritten to say the same thing
without its date, a date that named an incident now cites its live
check or commit, and one history sentence moved to ADR-005 §1. Rule 11
states the rule and `adr.py check` refuses a date in §2 to §8 outside a
path, a code span or the engine's own marks. Rule 10's example, which
put a date in the sentence, is removed.
