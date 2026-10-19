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

### Amendment 2026-10-13 — the interim line limit is 160

§7's interim rule, the line count lint enforces until the forwarder
shape replaces it, moves from 150 to 160 lines
(`tools/fabric/lint_rules/shape.py` BASH_LINE_LIMIT, its test, the
allowlist's description). The sshd drop-in's new settings and their
reason put `ssh-operator.sh` past 150. The owner's word, in the
coordinator's session: "go to 160 lines".

### Amendment 2026-10-14 — Wave 8 is done: no fabric command runs Node

The coordinator's job for Wave 8 (j44) still read "blocked on the
Node control plane's deletion" a day after it had happened; the owner
asked what blocked it, and the record was the stale part. What landed:
the Node control plane was deleted in #170 (4 work, 4 fix), once every
account's unit started the Python agent (read from the unit, the
`agentd.json` selector; the `fabric` op never carried an implementation
field, so §7's bullet planning one now says it was never built); the locale search server moved to
`tools/fabric/websearch_locale.py` in #174 (10 work, 4 fix), which
removed the Node server and its tests; #181 (4 work, 4 fix) deleted the
last Node tests of GZCoord and, in 2c9e8122, `tests/scratch.mjs`, the
last `.mjs` file. Read back on 2026-10-14: every account answers
`fabric-ctl all fabric` from 5a042a71, a head with no Node agent in it,
and this account's unit runs `tools/fabric/control/agentd.py` on
fabric-python. Rule 8 keeps its prohibition and loses its list of what
was not yet ported; it now says why CI still installs Node: a few tests
hold a Python helper to Node's own answers (`tests/test_control_js.py`).
§7's Wave 8 bullets stay as the record of how the cutover was run, with
a closing bullet; §8 states Waves 0 to 8 done and Wave 9 in progress, as
batch 1 (#200) and later batches have landed.

### Amendment 2026-10-19 — Wave 10: the managed projects' Node scripts move to Python

The owner asked, in the coordinator's session on 2026-10-19, for a plan
to move every remaining `.mjs` to Python, and then: "yes write adr
amendment and dispatch jobs to migrate the remaining". Rule 9 had kept
projects out of port waves, porting a script only when it next changed;
for Node this record now runs one wave. Measured on each project's
default branch that day: gzapp 7 files (1,696 lines), gzapp.decks 8
(1,092), blueteam.ee 1 (109), plus `astro.config.mjs` in blueteam.ee
and gzapi.ge, a framework's own configuration and so exempt. herdr's
three docs scripts came from its upstream (herdrdev/herdr, 8a6d6973):
the owner, asked, ruled that only the JavaScript we wrote is ported,
never a fork's upstream code, and the herdr port (#47) was closed. The owner added
that a project's TypeScript apps (gzapp's) are application code, not
scripts, and are never migrated.
Two scripts import a Node library with no obvious Python counterpart
(gzapp's glyph builder, fontnik; gzapp.decks' `doc.mjs`, puppeteer):
their holders decide port or exemption, and an exemption is added to
§7's table with why. gzapp's `apps/admin_web/scripts/import-table.mjs` is the first:
its holder showed it walks the pinned TypeScript compiler's AST, which
has no Python binding, and the coordinator accepted the exemption. Each port goes to the holder of its path in the
project's taxonomy, as a request from the coordinator. Rule 10 added,
§7's Wave 10 table, §8.

### Amendment 2026-10-19 — Wave 10: build-glyphs exempt; validate.js joins the wave

§7's Wave 10 table. The holder of both rows, devex-tooling, checked them
before porting (REPLY 01a15310, 2026-10-19), and the coordinator read the
files at gzapp's origin/HEAD:

- `tools/build_glyphs/build-glyphs.mjs` imports `fontnik` (FreeType and
  an SDF distance field, a native addon) and `@mapbox/glyph-pbf-composite`;
  PyPI has a binding for neither. Its `check` byte-compares the 256
  committed glyph ranges with a fresh render, so a Python rasteriser would
  change every range and need the Georgian labels checked again by eye, to
  change the language of a 271-line build script. The row's condition
  ("exempt if fontnik has no Python path") is met: exempt.
- The row said "its three tests". Only `deprecated-refs.test.mjs` tests
  `deprecated-refs.mjs`; `inline.test.mjs` and `success-body.test.mjs`
  import `inlineExternalRefs`, `MAX_REF_CHAIN`, `checkDocument` and
  `undescribedSuccessBodies` from `validate.js`, a `.js` script that rule
  10 left under rule 9. Ported alone they would need a Node bridge, a
  second harness for code still in Node. The holder offered two
  options: keep them beside `validate.js` under rule 9, or port
  `validate.js` (660 lines) now with them.
- The owner chose the second, and widened rule 10 with it: a `.js`
  or `.cjs` script of ours may join the wave, and one that is to be
  updated or fixed is ported instead of being changed in Node (in the
  coordinator's session, 2026-10-19). `validate.js` and its two tests
  are ported; the old script is the oracle on the four real documents.
  Its check 4 runs `@seriousme/openapi-schema-validator`; which Python
  validator replaces it (jsonschema with the OAS 3.1 meta-schema, or
  openapi-spec-validator) is the holder's choice, and a difference the
  oracle shows is reported, not hidden.

### Amendment 2026-10-19 — the provisioning entries are their modules

§5 rules 1 and 7. The owner asked devex-tooling to propose retiring
`runtime/provisioning/new-agent.sh`, a 16-line forwarder whose only work
beyond the exec was printing the pin's install command (REQUEST
01a15372); `store-enroll.sh` had the same shape. The coordinator took it
for both: the hint moves into the module, which re-execs itself under
the pin when it is present and prints the install command and exits 127
when it is not, so the provisioning a person runs has no shell in front
of it. A `bin/` command was not chosen, since every `bin/` entry is
itself a bash forwarder. python-dev-03 built it (#315); the old paths
say on stderr what replaces them for one release and are then deleted,
as rule 7's shim steps say.

### Amendment 2026-10-19 — a forwarder checks the pin before the module reads anything

§5 rule 5's fourth departure. Porting
`policies/check_repo_settings_carry_no_model_pins.sh` (Wave 9 batch 3),
the oracle's case "the python is asked for only once the file exists"
failed against the forwarder: the bash ran Python only when a settings
file was there, so a host without the pin and without the file exited 0,
while a forwarder of rule 1 checks the pin first and exits 127. That is
the departure the rule already allowed for an unknown verb, met through
a file instead; the rule now names any input, so each later port meets
it as a cited case instead of a fresh decision.

### Amendment 2026-10-19 — Wave 9 batch 5: the three Claude Code guards run on the pin

§5 rule 4. Wave 9 batch 5 ports the three Claude Code guards
(`model-switch-guard.sh`, `pipe-status-guard.sh`,
`subagent-clone-guard.sh`) to modules beside them, run on the pinned
interpreter; each `.sh` stays the path settings register, a forwarder
that fails closed (the model-switch guard asks, the other two deny)
when the pin or its module is missing. So `model-switch-guard.sh` is
no longer among the hooks that keep the host's `python3`. Their bash
tests are retired for the Python oracles of #320, which ran unchanged
against both.
