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

Fabric tooling is written in **Python 3.12 or newer, standard library
only**. Bash stays for what it is good at: forwarders and thin shims,
git hook entry points, the suite runners (`tests/run.sh`,
`tests/static.sh`), and step-runners whose body is mostly `sudo`, `ssh`
and installer calls. A tracked bash script over 150 lines is refused by
lint unless `policies/bash-allowlist.json` names it; the list starts as
the scripts that exist and only shrinks, each entry naming the wave that
ports it. A script is ported when it next needs a substantial change, or
in its wave, whichever comes first.

A port keeps the script's contract and its path. The path becomes a
shim until every caller, in the fabric and in the managed projects, has
moved.

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

1. New fabric tooling is Python 3.12+, standard library only. Bash is
   allowed for forwarders and shims, git hook entry points, `tests/run.sh`
   and `tests/static.sh`, and step-runners that are mostly `sudo`, `ssh`
   and installer calls.
2. `tools/fabric/lint.py` refuses a tracked bash script over 150 lines
   that `policies/bash-allowlist.json` does not name. An entry names its
   wave. Adding an entry is a finding; the list only shrinks.
3. A port freezes the script's contract first — its argv, the
   `AGENT_FABRIC_*` environment it reads, what goes to stdout and to
   stderr, its exit codes and its help text — in the new module's header.
4. A ported script keeps its path as a shim, running `/usr/bin/python3`,
   until every forwarder and caller is repointed; a sourced script's shim
   defines the same shell functions, each calling Python.
5. The script's existing bash test runs unchanged against the shim, as
   the parity oracle, in the port's pull request; the same pull request
   deletes the bash implementation, adds Python tests for the internals
   and removes the entry from the allowlist.
6. GitHub and git are called through `tools/fabric/gh.py` and
   `tools/fabric/git.py`: a body is passed on stdin or in a file, never
   interpolated; every call is bounded and names its operation in its
   error; JSON is parsed in Python, never with `jq`.

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

## 8. Decision Status

Accepted and in force. Wave 1, the GitHub toolkit, follows; the
allowlist holds the rest, each entry with its wave.

## References

- `policies/bash-allowlist.json`, `tools/fabric/lint.py`,
  `tools/fabric/gh.py`, `tools/fabric/git.py`.
- `tools/fabric/secrets_sync.py`: the first port, its contract frozen in
  its header, `runtime/provisioning/secrets/fabric-secrets` its shim.
- ADR-001 (the records), ADR-015 (code as memory), ADR-018 (the guards).
