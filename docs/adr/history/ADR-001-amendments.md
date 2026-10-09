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

### Amendment 2026-09-29 — The DIGEST is looked up, never read whole, and each entry has a word budget

An outside review said the governance corpus weighs on every agent. It
was measured before anything changed:
- A session loads about 8,400 tokens of fabric text: the launch prompt
  and CLAUDE.md. It loads no record.
- The DIGEST had grown to about 7,300 words, some 12,000 tokens. That is
  twice the launch prompt, and CLAUDE.md told every agent to read it
  first on any question about the fabric's rules.

The entries are useful (about 160 words each, the rules with their
sections), so they stay. What changes is how they are read:
- `fabric-adr lookup <topic>` answers only the matching entries.
- `fabric-adr lookup` alone answers the table of which record answers
  what, about 530 words.
- CLAUDE.md, the README, the fabric-decisions skill and the DIGEST's own
  header now say to look the DIGEST up, never to read it whole.
- `adr.py check` refuses an entry over 250 words, so a lookup stays
  cheap.

The two entries over the budget, ADR-029 and ADR-038, were tightened;
ADR-038's was also stale about paper recovery.

### Amendment 2026-10-09 — An exception to a direction covers what exists

The owner, 2026-10-09: "If a direction is set a carve out means for past." ADR-040's Wave 7 amendment (2026-10-04) set Python as the direction and said the control plane "stays Node". The owner read that as keeping existing code; the fabric's sessions read it as leave to keep developing there, and eight new Node modules were added to the control plane in five days, one helper among them called from Python across the language line. Nothing in the records said which reading was meant. Rule 12 makes the owner's the default for every record: an exception keeps the past, and new work follows the direction unless the exception says otherwise in words. ADR-040 rule 8 applies it to Node.
