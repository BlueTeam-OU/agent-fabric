#!/usr/bin/env bash
# runtime/github/pr-gate.sh — my open pull requests, their commits and
# what stands between each and main; --in-flight and --overlap for every
# branch on origin. The path is the contract (the managed projects'
# tools/gh/pr-gate.sh forward here); the work, its rules and every reason
# for them are in tools/fabric/github/pr_gate.py (ADR-040 §5 rule 4).
# Bash builtins only, to find it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
exec /usr/bin/python3 "$here/../../tools/fabric/github/pr_gate.py" "$@"
