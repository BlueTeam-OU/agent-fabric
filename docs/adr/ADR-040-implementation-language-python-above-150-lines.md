# ADR-040 — Implementation language: Python above 150 lines

**Date:** 2026-09-30
**Status:** Accepted
**Ratified:** owner, 2026-09-30, by the merge of agent-fabric #70 (f15baa2), which carried it, as §8 provided
**Decision Makers:** the owner (new fabric tooling in Python; a shell script ported when it next needs a substantial change; the wave plan); drafted by fabric-coordinator
**Scope:** every executable the fabric tracks — `bin/`, `runtime/`, `policies/`, `tools/`, `tests/`: the language a script is written in, the two kinds of bash that remain, and how an existing script moves; `policies/bash-allowlist.json` and the lint rule that reads it; `tools/fabric/gh.py` and `tools/fabric/git.py`
**Pillar:** P1

## 1. Context and Problem

The fabric grew in bash: about 10,500 lines of production shell in 65
scripts, and 8,800 lines of shell tests. Its bugs cluster in what bash
makes easy to get wrong. In one day on the secrets work:
- a `doppler()` wrapper function that `command -v` found instead of the binary;
- a timeout's exit code swallowed by `|| true` and read as "absent";
- an exit status taken from a pipe, where the last stage's status won;
- a YAML key matched only at the start of a line.

Each is invisible in review and each shipped. Several scripts already
embed Python in a heredoc for their real work (`fabric-secrets` did,
until it was ported), which gives the worst of both: a shell contract
around a program no linter reads. No shared Python layer for `gh` or
`git` exists: each Python tool calls them its own way.

## 2. Decision

Fabric tooling is written in **Python, standard library only**, and
runs on one pinned interpreter: `runtime/python.json` names it (3.13
today, a relocatable python-build-standalone build pinned by sha256),
installed once per host as `/usr/local/bin/fabric-python`; the code
stays valid on 3.13 and newer, the interpreters CI's matrix runs
(A 2026-10-01). Every fabric script is Python on it, bar two closed
kinds of bash (A 2026-10-11): the pre-Python installation path, which
runs where no interpreter exists yet, and the forwarder, which only
finds a Python module and execs it (rule 1). Other bash is ported in the
batches of Wave 9 (§7); a script is ported when it next needs a
substantial change, or in its batch, whichever comes first.

A port keeps the script's contract and its path. The path becomes a
shim until every caller, in the fabric and in the managed projects, has
moved; then the shim is retired, and what people and agents run is a
bare command. Shell that must run before the pinned Python exists stays
shell.

## 3. Alternatives Considered

- **Stay in bash, add shellcheck warnings as errors.** Catches quoting,
  not the logic bugs above; the embedded-Python scripts stay unread.
- **A rewrite in one pass.** Ten thousand lines behind one review is
  unreviewable, and the launcher starts every session: a regression
  there stops the fleet.
- **Node.** The control plane and GZCoord are already Node, but the
  fabric's tools, lint, routing and stores are Python; two general-purpose
  languages for the same kind of tool is the cost this decision avoids.
- **Python with dependencies.** Every account and every CI image would
  need them installed and pinned; the standard library covers subprocess,
  JSON, HTTP and argument parsing.

## 4. Rationale

The bugs are the language's, so the fix is the language. A size line is
checkable where "prefer Python" is not, and 150 lines is where the
existing shims and hooks end and the scripts with logic begin. An
allowlist that may only shrink turns the migration into a count that
lint enforces. Keeping paths and contracts lets the existing bash tests
serve as the parity oracle for each port, unchanged.

## 5. Binding Rules

1. Every fabric script is Python, standard library only, valid on 3.13
   and newer, the pin and the oldest system python3 of a supported
   platform, Debian 13's (A 2026-10-09), and runs on the pinned interpreter: `runtime/python.json`,
   installed per host by `tools/fabric/python_pin.py` (run as root by
   the host's own `/usr/bin/python3`, the hash checked before
   extraction) and reached as `/usr/local/bin/fabric-python`; CI installs
   the same build, and lint holds its minor version in CI's matrix
   (A 2026-10-01). Bash is allowed in two closed places and nowhere
   else (A 2026-10-11):
   - **The pre-Python installation path**: what runs before
     `python_pin.py install` has made `fabric-python`, or where it
     cannot be (a TemplateVM, an account before its interpreter, the
     boot of an AppVM), so that no interpreter is the reason and the
     only one. The list is closed, and `policies/bash-allowlist.json`
     holds it with each file's reason: the platform profiles and
     `packages.sh` under `runtime/provisioning/platform/` (sourced where
     only the host's shell exists; the CI smoke job installs the host
     contract from them); the Qubes scripts under `platform/qubes/`
     (`ssh-template.sh`, `ssh-operator.sh`, `ssh-restore.sh`,
     `agent-fabric-accounts.rc`); and under
     `runtime/provisioning/moveto/` `install.sh`, `enter` (a login-shell
     stub), `enter-ssh` (an sshd forced command) and `completion.bash`.
     Adding to the list is a finding. A script that is not on it is not
     pre-Python for being a step of provisioning: `bootstrap.sh`, the
     account creation and the host executor all need the pin; the first
     and the last are forwarders, the account creation its module by
     rule 7 (A 2026-10-19).
   - **The forwarder**: a file that finds its Python module, checks
     that the pin is installed and, if it is not, prints the command that
     installs it, and execs the module; at most 12 lines of code, comments
     and blank lines not counted, with no `case` and no loop. It carries
     no logic: a verb table, a refusal or a help text belongs to the
     module. It may pass on which signals were ignored, which Python's
     start-up erases. A guard the harness would read as no objection when
     it fails keeps a forwarder that fails closed in its own words, asking
     or denying, as `agent-dispatch-guard.sh` and `review-bash-guard.sh`
     do. A forwarder execs the pin; the suite runners' alone exec the
     host's `python3` (rule 4).

   The bin/ entry points and the hook entry points are forwarders of the
   second kind. Git runs a hook, and the harness a hook command, by path,
   so a hook's path stays a forwarder and its decision is a module on the
   pin; a Claude Code hook script is ported on the same terms, unless it
   is an entry on the first list. A forwarder that execs only a Python
   module keeps rule 7's bare commands consistent: the command people
   and agents run is its name on `PATH`, never the path of the module.
2. `tools/fabric/lint.py` refuses a tracked bash file that is neither
   on the pre-Python list in `policies/bash-allowlist.json` nor a
   forwarder by the shape of rule 1 (A 2026-10-11). A file is bash when
   it ends in `.sh` or `.bash` or its first line names `bash` or `sh`.
   The list has two sections: `stays`, the closed pre-Python list, whose
   every entry is a finding when added; and, while Wave 9 runs, `ports`,
   the files not yet ported, each naming its batch, which only shrinks
   and is empty when the wave ends. A forwarder is not listed; the
   150-line threshold is gone.
3. A port freezes the script's contract first — its argv, the
   `AGENT_FABRIC_*` environment it reads, what goes to stdout and to
   stderr, its exit codes and its help text — in the new module's header.
4. A ported script keeps its path as a shim, running the pinned
   interpreter (`${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}`,
   refusing with the install command when it is absent), until every
   forwarder and caller is repointed; a sourced script's shim defines the
   same shell functions, each calling Python, and fails the call, never
   its caller. Every entry point the fabric installs (`bin/`, the
   `policies/` checks a person or a hook runs, `fabric-secrets`) runs it.
   These keep the host's `python3`:
   - the hooks not yet ported — the git hooks and the Claude Code hooks
     (`session-start.sh`, `self-kill-guard.py`) —
     whose port moves them to the pin in Wave 9 (A 2026-10-11), as it moved
     the three guards of batch 5 (A 2026-10-19); the launcher, account creation and bootstrap
     have moved, and bootstrap's helpers under `runtime/` run on the pin
     with it, but for step 7's language-detector venv, which is made with
     the host's `python3`;
   - `check_actions_pinned_by_sha.py`, run by CI's static job, which
     installs no pin;
   - what `fabric-host` runs on another host, which may not have the pin
     yet;
   - the suite runners, which run the interpreter CI's matrix sets, to
     prove 3.13 and newer (A 2026-10-09); ported in Wave 9, their `.sh`
     paths stay forwarders to that interpreter (A 2026-10-11);
   - the Node scripts that ran fabric Python (GZCoord's `gzmsg.mjs` and
     `send.mjs`, the control agent's `jobs.mjs`, `ops.mjs` and
     `upgrade.mjs`) are gone with the Node (A 2026-10-14).
5. The script's existing bash test runs against the shim, as the parity
   oracle, in the port's pull request, its assertions unchanged. Four
   things in it may follow the port: its mock of `gh` may learn the
   transport `gh.py` uses beside the one it served, and the extended mock
   still passes the bash original; a case that reads the
   implementation's source, a constant or a scan, reads the module
   (A 2026-10-01); and a fixture that copies the scripts it runs copies
   their modules beside them, adding files and changing no assertion
   (A 2026-10-01). A fourth: a forwarder checks the pin before the module
   reads anything (its verb, its files, its environment), so a case run
   on a host without the pin expects the forwarder's 127 and its install
   line, not what the bash original did before it needed Python (a usage
   error, or a clean exit when there was nothing to check); the case
   says so and cites this rule (A 2026-10-19). The same pull request deletes the bash implementation,
   adds Python tests for the internals and removes the entry from the
   allowlist.
6. GitHub and git are called through `tools/fabric/gh.py` and
   `tools/fabric/git.py`: a body is passed on stdin or in a file, never
   interpolated; every call is bounded and names its operation in its
   error; JSON is parsed in Python, never with `jq`.
7. A fabric command is run by its bare name on `PATH`, never by a
   script path: a skill, a doc, a workflow, a hook message or a GZCoord
   message names `fabric-pr gate`, not `runtime/github/pr-gate.sh`
   (A 2026-10-08). A shim is retired in four steps: the bare command is
   added beside it; every caller moves, the managed projects' forwarders
   last; the old path says on stderr which command replaces it, for one
   release; it is deleted once every managed project's `fabric-ref` is
   past the move. A CI-only script is called through its module. Kept as shell: the
   pre-Python list and the forwarders of rule 1, and nothing else
   (A 2026-10-11). The `bin/` entry points, the host executor,
   `bootstrap.sh` and `moveto` are forwarders whose few lines of shell
   print the install command when the pin is absent; the git hooks and
   the suite runners are forwarders once ported. The two provisioning
   entries a person runs, `tools/fabric/new_agent.py` and
   `tools/fabric/store_enroll.py`, are their modules, run as `python3
   <agent-fabric>/tools/fabric/<module>.py`: before any import that
   needs the pin they re-exec under it, or print the install command and
   exit 127, so no shell stands in front of them; `new-agent.sh` and
   `store-enroll.sh` retire by the steps above (A 2026-10-19).
8. No new fabric code is written in Node. Wave 7's carve-out kept
   existing Node code as it was; it never admitted new modules into it,
   and none is admitted now (A 2026-10-09). No fabric command runs
   Node any more: the control plane, the locale search server, the shims
   and the Node test suites are gone. For fabric code Node stays only as
   an oracle a test calls to hold a Python helper to what Node answers
   (`tests/test_control_js.py`, `tests/test_control_sessions.py`), which
   is why CI still installs it; hosts keep Node for the managed projects
   (A 2026-10-14).
9. A managed project takes rule 1 as its own through its remit, and
   this record only advises it (A 2026-10-11): the project's code is its
   own (ADR-011). A bash script a project changes is ported in that
   change, a test that runs on a host is Python, and the same two kinds
   of bash stay (what runs before the project's interpreter exists, and
   the forwarder). There are no port waves in a project: a script that is
   not changed waits, and no agent is taken off current work to port it.
   The project's devex-tooling and architect-cto decide the order. The
   forwarders a project keeps to the fabric's commands (`tools/gh/*.sh`
   to `fabric-pr`) stay forwarders until rule 7 retires them.
10. A managed project's own Node scripts move to Python in Wave 10
   (§7), the one port wave a project has; the owner asked for it
   (A 2026-10-19). A `.mjs` file a project runs as a script, written
   by us, is ported, and none is added; one a fork took from the
   upstream it tracks stays the upstream's and is never ported (it
   would only make the fork diverge), and a project's application
   code (a TypeScript or JavaScript app, its packages and its build)
   is the product, in the language the product chose, never a script
   to port; a `.js` or `.cjs` script of ours may join the wave, and one
   that is to be updated or fixed is ported instead (A 2026-10-19). Exempt, and named in the wave's
   inventory with why: a framework's own configuration it loads itself
   (`astro.config.mjs`), and a script that works inside a Node library's
   API with no Python counterpart (gzapp's `import-table.mjs`, bound to
   the pinned TypeScript compiler). An
   exemption a holder finds is proposed to the coordinator and added to
   the inventory, never assumed. A port follows rules 3 to 5: the
   contract frozen, the command kept, the old script the oracle. Rule
   9's "no port waves in a project" stands for bash.

## 6. Consequences

- A port costs a review per wave and a parity run; a script that needs
  no change waits for its wave.
- Hooks pay Python's start-up (tens of milliseconds) where they were
  bash; the guards' wave measures it before and after.
- The managed projects' copies and forwarders are theirs: after a wave,
  their owners are told which module replaced which script.

## 7. Future Evolution

The waves: the GitHub toolkit, then the guards, then `bin/` and status,
then the launcher on its own, then the provisioning logic; the bash
tests migrate last. Waves 0 to 8 are the production scripts; Wave 9
(below) is the rest. The decision is done when the allowlist holds only
the pre-Python list.

Wave 7 is not bash: GZCoord's command-line tools, `gzmsg.mjs`,
`send.mjs` and `inbox.mjs` with the `i18n.mjs` they read, move to Python
together (A 2026-10-04). Their contract is frozen and their paths stay
as shims, as for any port. The functions the
control plane imports from them first move unchanged into one Node
module of its own. The CLI cases of the protocol suite run unchanged
against the shims; its unit cases are ported case for case; the two
validators agree on every message of the suite before the Node one goes.

Wave 8 moves the control plane (`runtime/control/`: the control agent,
`fabric-ctl`, `fabric-accounts` and every module they load) to Python
(A 2026-10-09). The locale search server stays Node until a change gives
it a reason to move.
- **Built beside, cut over once.** The Python control plane is a package
  under `tools/fabric/control/`, each Node module ported with its unit
  cases case for case; nothing runs it until the cutover. The Node tests
  stay the oracle until then.
- **The wire does not change.** Envelopes (`protocol.mjs`), op names,
  their arguments and replies, and the signed bytes are frozen: the
  payload's serialisation is Node's `JSON.stringify` to the byte
  (non-ASCII unescaped, integers without a fraction, no spaces), which
  Python's `json.dumps` does not give by default. So is the state the
  agent keeps on disk, which the Python agent takes over on the same
  account: the action ledger (its replay floor), the pool and its
  claims, the pressure ring, the tools report and the restart marker. A
  parity suite runs every op and action through both implementations
  against the same fixture homes, non-ASCII strings and numbers among
  the arguments and the persisted files among the fixtures, and compares
  the replies and the files. The fleet changes one account at a time, so
  a Python `fabric-ctl` must be answered by a Node control agent and the
  other way round.
- **Which agent answers is visible.** Planned as a field of the `fabric`
  op's reply; never built. The unit file told the two apart instead
  (the closing bullet below).
- **Ed25519 through the host's `openssl`** (`pkeyutl -rawin`): the
  primitive agrees with Node's byte for byte
  (docs/live-checks/2026-10-09-ed25519-through-openssl.md); the payload
  serialisation, the key formats and the key's path into openssl are
  the port's first checks. A key is never on a command line. `openssl`
  3 and the pinned `fabric-python` join the host contract that
  provisioning installs and audits, and every host is checked for both
  before its accounts switch.
- **The cross-language helpers go.** `fabric-jobs` reads the state stream
  itself, not through `queue.mjs`, and `roots.mjs` goes with the last Node
  caller of `roots.py`'s twin.
- **The cutover.** `bin/fabric-ctl` and `bin/fabric-accounts` switch
  fleet-wide when the cutover merges, since the launcher pulls main on
  every launch; that is safe because the wire is the same. The control
  agent's unit switches per account, because only a bootstrap rewrites
  it and a launcher's pull does not: one account first under a live
  read-back, then the fleet through `fabric-ctl all upgrade fabric`.
  The Node code is deleted only when every account's `fabric` op names
  `python`; deleted earlier, an account whose unit still starts the Node
  agent loses it and goes dark to the very upgrade that would fix it.
- **New wire behaviour waits.** An op, or an argument of an action, that
  only the Python agent knows is refused by every Node agent, whose
  arguments are a closed set (ADR-029 rule 3). New control-plane
  behaviour is written in the package from now on (rule 8) and enabled
  on the wire only once the Node code is deleted; until then it is
  outside the parity suite.
- **Done (A 2026-10-14).** The Node control plane was deleted in #170,
  and the last Node tests and `tests/scratch.mjs` in #181; the locale
  search server moved to `tools/fabric/websearch_locale.py` in #174. The
  tree holds no `.mjs` file. Which agent an account ran was read from
  its unit, not from the wire: the `runtime/control/agentd.json`
  selector until #170, now `tools/fabric/agentd_unit.py`'s
  `implementation_of` (the unit's ExecStart). New wire behaviour is no
  longer held back.

Wave 9 ports the rest of the fabric's bash (A 2026-10-11). Waves 0 to 8
moved the scripts that had logic of their own and left, by size and by
kind, hooks, bash tests, suite runners and step-runners; a bash test on
a host forked about four thousand processes in one run and nearly froze
it. Rule 1 now keeps two kinds of bash only, and Wave 9 ports every
other tracked bash file on main. The file-by-file inventory, with line
counts, is [docs/wave-9/inventory.md](../wave-9/inventory.md): 97 files
and 3,937 lines, of which 14 files are the pre-Python list, 46 are
forwarders, and 37 files (2,580 lines) are ported in ten batches. A
batch is one pull request: the module and its forwarder, the old bash
test running unchanged against it as the oracle (rule 5), then the
bash test replaced by a Python one case for case, and the allowlist
entries removed.

| batch | what | files | lines | lane |
|---|---|---|---|---|
| 1 | `fabric-pr`, `fabric-locale`, `fabric-secrets` dispatch; the secrets-sync fixture | 4 | 101 | python-dev |
| 2 | `fabric-role`, `fabric-review` dispatch | 2 | 85 | fabric-coordinator |
| 3 | `policies/` checks and their tests | 3 | 274 | fabric-coordinator |
| 4 | git hooks and their helpers | 5 | 341 | fabric-coordinator |
| 5 | Claude Code guards and their tests | 6 | 415 | fabric-coordinator |
| 6 | Claude Code session hooks and their tests | 5 | 392 | fabric-coordinator |
| 7 | status line and tab title | 3 | 311 | fabric-coordinator |
| 8 | installer tests under `runtime/claude-code/` | 2 | 293 | fabric-coordinator |
| 9 | language detector installer; gzapp host check | 3 | 89 | fabric-coordinator |
| 10 | suite runners and leak check, last | 4 | 279 | fabric-coordinator |

The lane is who may commit the batch: python-dev's contributor entry
(`policies/authority.json`), or the coordinator, because the batch's
paths are on `CONTRIBUTOR_NEVER` in `tools/fabric/lint.py` or no entry
names them. Batches 1 to 9 are independent of each other; batch 10 is
last because the suite runner lists the bash suites the others retire.
Until then the order within the wave is the coordinator's.

Lint changes in a pull request of its own, before batch 1 (it is
`tools/fabric/lint.py` and so the coordinator's): the allowlist
`scripts` map becomes the two sections of rule 2, seeded with the
pre-Python list and the files of the table above, each naming its batch;
the 150-line rule is replaced by the forwarder shape (at most 12 lines of
code, no `case`, no loop); the file kinds it reads grow from `*.sh` to
`*.sh`, `*.bash` and a bash shebang, so an extensionless hook is seen; and
a finding names the rule a file breaks. Seeding `ports` is the one time
adding to the list is not a finding. Until that change merges, a
line rule is what lint enforces: 160 lines (A 2026-10-13).

Wave 10 ports the managed projects' Node scripts. When it was set the
projects held 16 `.mjs` scripts of their own, 2,897 lines, beside the
framework configurations; the fabric itself has none since Wave 8.
Each port is the holder's of the path in its project's taxonomy, one
pull request per project and holder, under that project's arming rules.

| project | what | files | lines | holder | note |
|---|---|---|---|---|---|
| gzapp | `tools/validate_api_surface/`: `deprecated-refs.mjs`, `validate.js` and their three tests | 5 | 1,601 | devex-tooling | YAML: the project's own dependency, not the fabric's standard-library rule. `validate.js` joins the wave with the two tests that import it; the old script is the oracle on the four real documents, and the OpenAPI validator that replaces its check 4 is the holder's choice |
| gzapp | `tools/one-shot/split_adr_amendments.mjs` | 1 | 327 | devex-tooling | deleted, not ported: it ran once |
| gzapp | `tools/build_glyphs/build-glyphs.mjs` | 1 | 271 | devex-tooling | exempt: fontnik and `@mapbox/glyph-pbf-composite` are native Node addons with no Python binding, and `check` compares the committed glyph ranges byte for byte with a fresh render, which a Python rasteriser would not reproduce (its holder's finding) |
| gzapp | `apps/admin_web/scripts/import-table.mjs` | 1 | 157 | web-dev | exempt: it walks the AST of the project's pinned TypeScript compiler, which has no Python binding; a re-implementation missed real imports (its holder's proposal) |
| gzapp.decks | `scripts/*.mjs` | 8 | 1,092 | brand-comms | `doc.mjs` drives puppeteer: exempt or ported to the fleet's browser, the holder says |
| blueteam.ee | `deploy/check-dist.mjs` | 1 | 109 | edge-hosting | the taxonomy's note gives it the deploy; its paths are empty |

`astro.config.mjs` in blueteam.ee and gzapi.ge is exempt (rule 10). herdr's `scripts/docs/*.mjs` came from
the upstream FleetDeck tracks (`herdrdev/herdr`) and stay as they are.

## 8. Decision Status

Accepted and in force. Waves 0 to 8 are done: the bash allowlist is
empty, and no fabric command runs Node (the control plane, the locale
search server and the GZCoord tools are Python). Wave 9,
the rest of the bash, is in progress in ten batches; Wave 10, the
managed projects' Node scripts, is dispatched (A 2026-10-19).

## References

- `policies/bash-allowlist.json`, `tools/fabric/lint.py`,
  `tools/fabric/gh.py`, `tools/fabric/git.py`.
- `docs/wave-9/inventory.md`: every tracked bash file, classified.
- `tools/fabric/secrets_sync.py`: the first port, its contract frozen in
  its header, `runtime/provisioning/secrets/fabric-secrets` its shim.
- ADR-001 (the records), ADR-015 (code as memory), ADR-018 (the guards).

## Amendments

The body above reads current; each change's full note is in [history/ADR-040-amendments.md](history/ADR-040-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-01 | The oracle's mock and its source reads may follow the port | §5 rule 5: the oracle's mock may learn gh.py's transport, and a case reading the source reads the module |
| 2026-10-01 | One pinned Python, 3.13, installed per host | §2, §5 rules 1 and 4: `runtime/python.json`, `python_pin.py`, `fabric-python`; shims run it; CI installs it |
| 2026-10-01 | A fixture may copy the modules of the scripts it copies | §5 rule 5: a third departure for the oracle, files added and no assertion changed |
| 2026-10-04 | Wave 7: GZCoord's command-line tools move to Python | §7: send, inbox and gzmsg port together, the control plane's imports split out first, the protocol suite the oracle |
| 2026-10-08 | Shims retire; commands run by bare name | §2, §5 rule 7: a caller names the command on PATH; a shim retires in four steps once its callers move; shell before the pinned Python stays shell |
| 2026-10-09 | Wave 8: the control plane moves to Python | §5 waves: the control plane (`runtime/control/`) is built beside in Python, wire frozen, Ed25519 through openssl, cut over once; Wave 7's carve-out of the control plane withdrawn; rule 8 added: no new fabric code in Node |
| 2026-10-09 | Valid on 3.13 and newer; CI's Python legs halved | §2 and §5 rule 1: the floor is 3.13, the pin and the oldest supported system python3; CI runs the Python suites on 3.13 and 3.14 |
| 2026-10-11 | Wave 9: the rest of the bash moves to Python | §2, §5 rules 1, 2, 4, 5, 7 and 9, §7: Python bar the pre-Python list and the forwarder; the 150-line rule goes; 37 files in ten batches; managed projects advised |
| 2026-10-13 | the interim line limit is 160 | §7 |
| 2026-10-14 | Wave 8 is done: no fabric command runs Node | §5 rule 8, §7, §8: the Node control plane, locale search server, shims and Node suites are gone (#170, #174, #181); Node stays only as a test oracle; new wire behaviour is no longer held back |
| 2026-10-19 | Wave 10: the managed projects' Node scripts move to Python | §5 rule 10, §7, §8: the owner's request; 16 `.mjs` scripts of their own: four ports, one deletion, one exemption, one decision with its holder; a fork's upstream code never ported; framework configuration and a Node-API-bound script exempt, named |
| 2026-10-19 | Wave 10: build-glyphs exempt; validate.js joins the wave | §5 rule 10: a `.js` script of ours may join the wave, and one to be updated or fixed is ported instead; §7's Wave 10 table: `build-glyphs.mjs` exempt, `validate.js` and its two tests ported |
| 2026-10-19 | the provisioning entries are their modules | §5 rules 1 and 7: `new_agent.py` and `store_enroll.py` are the entries, re-exec under the pin or print its install command; `new-agent.sh` and `store-enroll.sh` retire by the shim steps |
| 2026-10-19 | a forwarder checks the pin before the module reads anything | §5 rule 5: the fourth departure covers any input the bash read before it needed Python, not only a verb |
| 2026-10-19 | Wave 9 batch 5: the three Claude Code guards run on the pin | §5 rule 4: `model-switch-guard.sh` leaves the host-`python3` list; it, `pipe-status-guard.sh` and `subagent-clone-guard.sh` are fail-closed forwarders to modules on the pin |
