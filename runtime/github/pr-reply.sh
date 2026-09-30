#!/usr/bin/env bash
# runtime/github/pr-reply.sh — reply to ONE review thread and resolve it.
# The path is the contract (the managed projects' tools/gh/pr-reply.sh
# forward here); the work, its rules and every reason for them are in
# tools/fabric/github/pr_reply.py (ADR-040 §5 rule 4). Bash builtins
# only, to find it: with git or hostname missing from PATH the module must
# still run, and say which (dirname and readlink are not builtins).
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
exec /usr/bin/python3 "$here/../../tools/fabric/github/pr_reply.py" "$@"
