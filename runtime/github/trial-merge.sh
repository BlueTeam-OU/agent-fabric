#!/usr/bin/env bash
# runtime/github/trial-merge.sh — do these branches combine? The path is the
# contract (pr-gate's comments and the agents' procedures name it); the
# work, its rules and every reason for them are in
# tools/fabric/github/trial_merge.py (ADR-040 §5 rule 4). Bash builtins
# only, to find it: with git or hostname missing from PATH the module must
# still run, and say which.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
exec /usr/bin/python3 "$here/../../tools/fabric/github/trial_merge.py" "$@"
