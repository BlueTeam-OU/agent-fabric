#!/usr/bin/env bash
# runtime/github/post-review.sh — post THE review of a PR, marked so the
# gate counts it. The path is the contract (the managed projects'
# tools/gh/post-review.sh forward here); the work, its rules and every
# reason for them are in tools/fabric/github/post_review.py (ADR-040 §5
# rule 4). Bash builtins only, to find it: with git or hostname missing
# from PATH the module must still run, and say which.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
exec /usr/bin/python3 "$here/../../tools/fabric/github/post_review.py" "$@"
