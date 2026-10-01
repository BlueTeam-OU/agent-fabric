#!/usr/bin/env bash
# runtime/github/commit-class.sh — sourced, not run: the shim that keeps the
# classifier's shell functions for pr-gate.sh and the managed projects'
# forwarders (projects/<id>/integration/gh/commit-class.sh sources this
# path). The rule and every reason for it live in
# tools/fabric/github/commit_class.py (ADR-040 §5 rule 4: a sourced script's
# shim defines the same functions, each calling Python).
#
#   commit_class <parents> <subject> [<answers>] [<pr>] [<owner/repo>]   → prints merge | fix | work
#   revert_targets                                                        stdin: a commit body → the shas it reverts
_COMMIT_CLASS_PY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)/tools/fabric/github/commit_class.py"
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
# Sourced: a name of its own in the caller's shell, and a missing
# interpreter fails the call (return), never the caller (exit).
_COMMIT_CLASS_PYTHON="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
_commit_class_run() {
  [[ -x "$_COMMIT_CLASS_PYTHON" ]] || { echo "commit-class.sh: the fleet's pinned Python is not installed at $_COMMIT_CLASS_PYTHON; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; return 127; }
  "$_COMMIT_CLASS_PYTHON" "$_COMMIT_CLASS_PY" "$@"
}
commit_class() { _commit_class_run class "$@"; }
revert_targets() { _commit_class_run revert-targets; }
