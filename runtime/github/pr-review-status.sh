#!/usr/bin/env bash
# runtime/github/pr-review-status.sh — has THE HEAD of this PR been reviewed?
# The path is the contract (the managed projects' tools/gh/pr-review-status.sh
# forward here, through projects/<id>/integration/gh/); the work, its rules and
# every reason for them are in tools/fabric/github/pr_review_status.py
# (ADR-040 §5 rule 4). Bash builtins only, to find it: dirname and readlink
# are not builtins, and the module must still run, and say what is missing,
# with tools off PATH.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
exec /usr/bin/python3 "$here/../../tools/fabric/github/pr_review_status.py" "$@"
