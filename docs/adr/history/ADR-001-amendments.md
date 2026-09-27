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
