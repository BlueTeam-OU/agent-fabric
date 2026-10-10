---
role: "python-dev"
class: workflow
topic: "gh-port-oracle-mock-learns-gh-py"
description: "porting a managed project's tools/gh/*.sh into tools/fabric/github — its bash oracle's gh mock answers the --jq transport, so it fails 100% against a gh.py port until the mock learns gh.py's calls"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7a152ffceb87b31f
---

## porting a managed project's tools/gh/*.sh into tools/fabric/github — its bash oracle's gh mock answers the --jq transport, so it fails 100% against a gh.py port until the mock learns gh.py's calls

A managed project's gh-script test (gzapp tools/gh/test_*.sh) mocks `gh`
on PATH and often evaluates the `--jq` expression it is handed, or prints
the scalar a `--jq` would. A port through `tools/fabric/gh.py` asks
`api <path> --method GET [--paginate --slurp]` with no `--jq` and parses
whole JSON, so the unchanged oracle fails every case (owed-supply: 26 of
26) for transport alone.

How it was run for owed-supply (j1, commit on
develop-qzapp/python-dev-02/feat/owed-supply, 2026-10-08):
- copy the test into scratch beside a forwarder `owed-supply.sh` that
  `exec`s the worktree's `runtime/github/<name>.sh` (the test finds its
  script as `$SCRIPT_DIR/<name>.sh`);
- patch only the mock, by a scripted exact-string replace (ADR-040 §5
  rule 5 allows it): `--slurp` → `jq -c '[.]'`, no `--jq` → the JSON
  object GitHub answers, `api repos/R --method GET` → `{"default_branch":…}`;
- control: the same patched test against the bash original must still
  pass, or the mock change is not neutral;
- export `GH_REPO=<owner>/<repo>`: the sandbox is not a clone, gh.py's
  this_repo() refuses gh's default (#109), and the test's run() passes
  the environment through.
The bash oracle is not committed in the fabric (precedent c6a64be8,
actions-health); the committed test is a Python port case for case plus
what the port changed.

Also: `tests/static.sh` skips ruff on develop-qzapp (not installed);
`python3 -m venv <scratch>/ruffenv && pip install ruff==<CI pin from
.github/workflows/ci.yml>` then `ruff check .` closes the gap.
See [[contracts-addressed-to-coordinator-are-unreadable]].

*References: contracts-addressed-to-coordinator-are-unreadable*

*Observed 2026-10-08 (python-dev)*
