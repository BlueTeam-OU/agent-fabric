# ADR-040 — Implementation language: Python above 150 lines

**Date:** 2026-09-30
**Status:** Accepted
**Ratified:** owner, 2026-09-30, by the merge of agent-fabric #70 (f15baa2), which carried it, as §8 provided
**Decision Makers:** the owner (new fabric tooling in Python; a shell script ported when it next needs a substantial change; the wave plan); drafted by fabric-coordinator
**Scope:** every executable the fabric tracks — `bin/`, `runtime/`, `policies/`, `tools/`, `tests/`: the language a new one is written in, the size a bash one may reach, and how an existing one moves; `policies/bash-allowlist.json` and the lint rule that reads it; `tools/fabric/gh.py` and `tools/fabric/git.py`
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
stays valid on 3.12 and newer, the interpreters CI's matrix runs
(A 2026-10-01). Bash stays for what it is good at: forwarders and thin shims,
git hook entry points, the suite runners (`tests/run.sh`,
`tests/static.sh`), and step-runners whose body is mostly `sudo`, `ssh`
and installer calls. A tracked bash script over 150 lines is refused by
lint unless `policies/bash-allowlist.json` names it; the list starts as
the scripts that exist and only shrinks, each entry naming the wave that
ports it. A script is ported when it next needs a substantial change, or
in its wave, whichever comes first.

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

1. New fabric tooling is Python, standard library only, valid on 3.12
   and newer, and runs on the pinned interpreter: `runtime/python.json`,
   installed per host by `tools/fabric/python_pin.py` (run as root by
   the host's own `/usr/bin/python3`, the hash checked before
   extraction) and reached as `/usr/local/bin/fabric-python`; CI installs
   the same build, and lint holds its minor version in CI's matrix
   (A 2026-10-01). Bash is
   allowed for forwarders and shims, git hook entry points, `tests/run.sh`
   and `tests/static.sh`, and step-runners that are mostly `sudo`, `ssh`
   and installer calls.
2. `tools/fabric/lint.py` refuses a tracked bash script over 150 lines
   that `policies/bash-allowlist.json` does not name. An entry names its
   wave. Adding an entry is a finding; the list only shrinks.
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
     (`session-start.sh`, `model-switch-guard.sh`, `self-kill-guard.py`) —
     whose port moves them; the launcher, account creation and bootstrap
     have moved, and bootstrap's helpers under `runtime/` run on the pin
     with it, but for step 7's language-detector venv, which is made with
     the host's `python3`;
   - `check_actions_pinned_by_sha.py`, run by CI's static job, which
     installs no pin;
   - what `fabric-host` runs on another host, which may not have the pin
     yet;
   - the suite runners, which run the interpreter CI's matrix sets, to
     prove 3.12 and newer (A 2026-10-01);
   - the Node scripts that run fabric Python — GZCoord's `gzmsg.mjs`
     (whoami) and `send.mjs` (job intake), and the control agent's
     `jobs.mjs`, `ops.mjs` and `upgrade.mjs` — which keep it until they
     are repointed; `send.mjs`'s journal already runs the pin
     (ADR-041) (A 2026-10-01).
5. The script's existing bash test runs against the shim, as the parity
   oracle, in the port's pull request, its assertions unchanged. Three
   things in it may follow the port: its mock of `gh` may learn the
   transport `gh.py` uses beside the one it served, and the extended mock
   still passes the bash original; a case that reads the
   implementation's source, a constant or a scan, reads the module
   (A 2026-10-01); and a fixture that copies the scripts it runs copies
   their modules beside them, adding files and changing no assertion
   (A 2026-10-01). The same pull request deletes the bash implementation,
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
   past the move. A CI-only script is called through its module. Never
   migrated, and kept as shell: what runs before the pinned Python
   exists or says how to install it — the host and account provisioning
   chain (`runtime/provisioning/platform/`, `new-agent.sh` and its
   worker, `persist-accounts.sh`, `rename-working-copy.sh`), the host
   executor, `bootstrap.sh`, `moveto`, and the `bin/` entry points,
   whose few lines of shell print the install command when the pin is
   absent — and the git hooks and the suite runners (rule 1).
8. No new fabric code is written in Node. The remaining Node (the
   control plane until Wave 8's cutover, the locale search server) takes
   fixes where it is; new behaviour of the control plane is written in
   the Python package and is live from the cutover (A 2026-10-09).

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
tests migrate last. The decision is done when the allowlist holds no
production script.

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
  their arguments and replies, and the signature bytes are frozen. A
  parity suite runs every op and action through both implementations
  against the same fixture homes and compares the replies. The fleet
  upgrades one account at a time, so a Python `fabric-ctl` must be
  answered by a Node control agent and the other way round.
- **Ed25519 through the host's `openssl`** (`pkeyutl -rawin`): measured
  byte-identical with Node (docs/live-checks/2026-10-09-ed25519-through-openssl.md).
  A key is never on a command line.
- **The cross-language helpers go.** `fabric-jobs` reads the state stream
  itself, not through `queue.mjs`, and `roots.mjs` goes with the last Node
  caller of `roots.py`'s twin.
- **The cutover** switches `bin/fabric-ctl`, `bin/fabric-accounts` and
  the control agent's unit together, one account first under a live
  read-back, then the fleet through `fabric-ctl all upgrade fabric`; the
  Node code is deleted once every account reports the Python agent.

## 8. Decision Status

Accepted and in force. Wave 1, the GitHub toolkit, follows; the
allowlist holds the rest, each entry with its wave.

## References

- `policies/bash-allowlist.json`, `tools/fabric/lint.py`,
  `tools/fabric/gh.py`, `tools/fabric/git.py`.
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
