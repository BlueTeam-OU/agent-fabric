# ADR-040 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-01 — The oracle's mock and its source reads may follow the port

Rule 5 said the bash test runs "unchanged" against the shim. The first
four ports of Wave 1 showed that two parts of a test cannot stay as they
were, while its assertions can and did.

The mock of `gh`. A mock answers the argv the bash sent: `-f body=…`,
`--jq` filters, one request per page. `gh.py` sends a body as JSON on
stdin and pages with `--slurp`, so the mocks of pr-reply and
pr-review-status learned those shapes beside the old ones. Each extended
mock was run against the bash original first, which passed it; only
then against the shim.

The source reads. Two cases read the implementation's text rather than
running it: post-review's check that its review marker equals the
reader's, and pr-review-status's scan for jq-only flags handed to
`gh api`. Against a three-line shim the first failed and the second
passed on nothing. They read the modules now; a flag planted in the
module fails the scan.

Neither change touches what an assertion asks, and the extended mock's
pass on the original bash is what keeps "parity" meaning the same
behaviour.
