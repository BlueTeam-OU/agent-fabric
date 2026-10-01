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
commit_class() { /usr/bin/python3 "$_COMMIT_CLASS_PY" class "$@"; }
revert_targets() { /usr/bin/python3 "$_COMMIT_CLASS_PY" revert-targets; }
