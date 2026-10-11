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


### Amendment 2026-10-09 — Wave 8: the control plane moves to Python

The owner's decision, 2026-10-09: "B, use agents you have to convert", choosing, after seeing new `.mjs` modules appear, to move the control plane to Python rather than only fence new Node out of it. Wave 7 (2026-10-04) had said the control plane "stays Node"; the owner meant the existing code, and the fabric's sessions read it as leave to keep developing there: eight modules were added since, and a Node helper that Python's `fabric-jobs` calls across the language line (`queue.mjs`), the seam Wave 7 removed from GZCoord. ADR-001 rule 12 now makes the owner's reading the default for every exception; rule 8 applies it here. The port is built beside the Node control plane with the wire frozen, because the fleet upgrades one account at a time and a mixed fleet must keep answering. Ed25519 is the one capability the standard library lacks; the host's openssl's primitive agrees with Node's byte for byte (docs/live-checks/2026-10-09-ed25519-through-openssl.md), and the serialisation of what is signed, the key formats and the key's path are the port's first checks. #131's review shaped the rest: the persisted state is frozen with the wire; the `fabric` op names its implementation, because nothing else on a frozen wire tells the agents apart and deleting the Node too early would leave an account's old unit starting a missing agent; `bin/` switches on merge and the unit per account; new wire behaviour waits for the Node to go; openssl and fabric-python join the host contract. Rule 8 stops new Node meanwhile. The locale search server stays Node: no change asks for it yet.

### Amendment 2026-10-09 — Valid on 3.13 and newer; CI's Python legs halved

The owner asked why CI ran four Python legs (3.12 twice, 3.13, 3.14). Since the 2026-10-01 amendment every fabric tool runs on the pinned fabric-python 3.13; what still runs on a host's own python3 (the installer, the git and Claude Code hooks, bootstrap) meets the supported platforms' system Pythons: Fedora's 3.14 and Debian 13's 3.13 (the platform-smoke containers run the suites on both). No host runs 3.12, so the promise moves to 3.13 and CI's Python section runs two legs, 3.13 with Node 20 (the oldest Node the control plane must start on, until Wave 8 deletes it) and 3.14 with Node 22. The owner approved it the same day.

### Amendment 2026-10-11 — Wave 9: the rest of the bash moves to Python

The owner's decision, 2026-10-11: "we should move remaining scripts to python where it's not part of first installation process (python still not provided)". Asked how far it reaches, the owner chose agent-fabric now, and the managed projects (gzapp, InterWeave, herdr, the gateway) take the rule but port a script when they next change it, with any test that runs locally, and no dedicated port waves that would take agents off current work. The trigger was a local bash test in gzapp (`tools/checks/test_require_template_vm.sh`) that forked about 4,000 processes and nearly froze the host; devex-tooling's Python port fixed it.

Rule 1 had kept bash for forwarders, hooks, the suite runners and step-runners, and rule 2 let a script under 150 lines be bash whatever it did; by size and by kind that left 97 tracked bash files and 3,937 lines. The rule now keeps two closed kinds. The pre-Python installation path is what runs before `python_pin.py install` (which itself runs on the host's `/usr/bin/python3`) or where the pin cannot be: the platform profiles and `packages.sh`, the four Qubes scripts, and moveto's `install.sh`, `enter`, `enter-ssh` and `completion.bash`: 14 files. Reading `runtime/provisioning/` and `bootstrap.py` settled that `bootstrap.sh`, `new-agent.sh`, its worker, the host executor and `store-enroll.sh` are not on it: each already refuses without the pin and prints the install command, so each is a forwarder. The forwarder is the second kind, and what it may hold is measured so that lint can check it: at most 12 lines of code, no `case`, no loop. That moves the verb tables and refusals of `fabric-pr`, `fabric-role`, `fabric-review`, `fabric-locale` and `fabric-secrets` into their modules.

Git hooks and Claude Code hook scripts become Python on the pin unless they run before it; none does, since bootstrap, which installs them, needs the pin. Their paths stay forwarders because git and the harness run a file by path, and the two PreToolUse guards that already fail closed keep that shape. The suite runners are ported with their `.sh` paths staying forwarders to the host's `python3`, the interpreter CI's matrix sets. Rule 7's list of what is "never migrated" is replaced by a reference to rule 1, so that the two cannot disagree.

The inventory (`docs/wave-9/inventory.md`) classifies every file and groups the 37 that port (2,580 lines) into ten batches of one pull request each. All but batch 1 are on the coordinator's side of the contributor wall (`policies/`, `runtime/claude-code/`, `tests/run.sh`, or a path no entry names), so python-dev's entry covers 101 of the 2,580 lines unless the owner widens it; this record does not. Lint changes in a pull request of its own: the 150-line rule is replaced by the forwarder shape and a closed list, with a one-time seeded `ports` section that only shrinks. Rule 9 is advice to the managed projects, whose code is theirs: a bash script they change is ported in that change, a host test is Python, no port waves, and their devex-tooling and architect-cto decide the order.

Rule 5 gains a fourth departure the parity test may take, found by batch 1 (`fabric-pr`, python-dev-04's #200): the forwarder checks the pin before the module reads the verb, so on a host without the pin an unknown verb exits 127 with the install line, where the bash original printed its usage. The case says so and cites the rule.
