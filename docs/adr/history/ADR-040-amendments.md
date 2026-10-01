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

One assertion did change with them: the scan's list of flags gh does
not have lost `--slurp`, which gh api has had since 2.48 and gh.py
pages with; kept, the scan would have refused the transport the port
uses. Every other assertion asks what it asked, and the extended mock's
pass on the original bash is what keeps "parity" meaning the same
behaviour.

### Amendment 2026-10-01 — One pinned Python, 3.13, installed per host

The owner decided that the fleet runs one tagged Python rather than
whatever each host's packages provide, for compatibility across agents,
and chose 3.13 as the first step of Wave 5. The shape follows what was
agreed then, with one change: the installer is Python (`python_pin.py`,
run by the host's own `/usr/bin/python3`, which the host contract
already requires) rather than a bash step-runner, so it is tested like
the rest. Read back on develop-qzapp: the build installed, ran for
another account, and a fabric suite passed on it; two lint cases failed
there, because lint's schema fallback skipped keywords jsonschema
checks, and on a standard-library interpreter the fallback is the
validator — fixed in the same pull request, with a rule that refuses a
schema keyword the fallback does not check.
