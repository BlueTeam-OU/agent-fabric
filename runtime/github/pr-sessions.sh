#!/usr/bin/env bash
# runtime/github/pr-sessions.sh — which session owns which PR, newest first.
# The path is the contract (the managed projects' tools/gh/pr-sessions.sh
# forward here); the work, its rules and every reason for them are in
# tools/fabric/github/pr_sessions.py (ADR-040 §5 rule 4). Bash builtins
# only, to find it: dirname and readlink are not builtins, and the module
# must still run, and say what is missing, with tools off PATH.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
exec /usr/bin/python3 "$here/../../tools/fabric/github/pr_sessions.py" "$@"
