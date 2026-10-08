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

### Amendment 2026-10-01 — A fixture may copy the modules of the scripts it copies

Wave 5's oracle for account creation, `test_new-agent.sh`, builds a
fixture fabric: it copies the scripts under test into it, beside fakes
of what they call, and runs the copies. Behind a shim, a copied script
finds no module, so the oracle could not run the port at all. The
smallest change that lets it is the fixture copying the two modules
too: files added, no assertion changed, and the bash original still
passes the same fixture. The alternatives were worse: running the
oracle against the live tree gives up the fakes that keep it off real
accounts, and rewriting the fixture loses the parity the unchanged
oracle stands for. A worker whose body is `sudo`, `useradd` and
installer calls stays a bash step-runner under rule 1, its decisions in
Python; the fixture rule does not widen what is ported.

### Amendment 2026-10-04 — Wave 7: GZCoord's command-line tools move to Python

The owner's decision, after the coordinator's recommendation. The
fabric's Node had stayed outside the port: it is a tested language, not
bash. Two seams made three of its files worth moving. `send.mjs` and
`inbox.mjs` start the Python journal (`episodic.py`) as a process on
every send and every inbox page, and that crossing is where the
journal's edge cases kept appearing in review (#78, #84, #88).
`gzmsg.mjs` holds the only copy of the message validator, which the
Python tools reach only through `inbox.mjs`. Moved together, the send,
the inbox, the validator and the journal are one language, in one
process per message.

What stays Node: the control plane (`runtime/control/`) and the locale
search server (`runtime/mcp/websearch-locale/server.mjs`). They are
self-contained and tested, and the daemon is an event loop Node suits;
moving them would be churn with no defect behind it.

The control plane imports, as a library, `whoami`, `FABRIC_ROOT`,
`findTaxonomy` and `loadTaxonomy` from `gzmsg.mjs`, and `api`,
`identity`, `integrationConfig`, `inboxRoot`, `token`, `syncedToken`,
`syncedVar` and `holdStatus` from `inbox.mjs`; the search server imports
`syncedVar`. Those move first, unchanged, into one Node module the
control plane owns, so the daemon never depends on a script that becomes
a shim. They are then two implementations of identity and the relay's
API, a Node one and the Python one `relay.py` already is; the control
plane's tests and the port's tests each hold their own.

The oracle: the protocol suite's cases that run the scripts as commands
run unchanged against the shims. Its cases that import functions are
ported to Python, case for case, the way the bash tests were. Before the
Node validator is removed, both validators run over every message the
suite holds and agree on every verdict. The journal's order — a send
kept before it is posted, a page journaled before it is acknowledged —
is what those cases pin, and the port keeps it. The wire grammar is
frozen; nothing here changes what a message is. The locale dictionaries
stay the JSON they are, read by the Python as they were by the Node.


### Amendment 2026-10-08 — Shims retire; commands run by bare name

Rule 4 kept a ported script's path as a shim "until every forwarder and
caller is repointed", and nothing ever repointed them: a week after the
last wave, 57 shell files still ran a Python module, the fabric named
`pr-gate.sh` in 25 places, and the managed projects' `tools/gh/*.sh`
forwarded to those shims, two layers deep. The owner asked for them to
be phased out, and to leave alone what has to run before Python is
installed. Rule 7 names the end state (a bare command on `PATH`), the
four steps a shim takes to retire, and the scripts that stay shell
because they run before the pinned interpreter exists or are what tells
a person how to install it.

