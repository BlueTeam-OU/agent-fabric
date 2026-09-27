# ADR-023 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-09-27 — A receiver stands down on a pushed branch too

Rule 4, the sender's choice of holder, was corrected on agent-fabric #52
(a review thread) to read `pr-gate.sh --in-flight --path <prefix>`: a job
waiting for its PR sits on a pushed branch that `--all`, which lists open
PRs only, never shows. Rule 5, the receiver's stand-down check, still
read open PRs only, so the sender and the receiver disagreed about the
same sibling (the re-review of #52). Rule 5 now stands down on a
sibling's pushed branch as well, found by the same query, and the
gzcoord-receive skill's step says the same. §7's note that the query
"can" be read by rule 4 is dropped: rule 4 reads it.
