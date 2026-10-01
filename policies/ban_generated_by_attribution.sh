#!/usr/bin/env bash
# policies/ban_generated_by_attribution.sh — ban machine attribution from the
# commits a branch adds and from the pull-request description. The path is
# the contract (ci.yml and tests/run.sh name it); the work, its rules and
# every reason for them are in
# tools/fabric/guards/ban_generated_by_attribution.py (ADR-040 §5 rule 4).
# Bash builtins only, to find it: with git or hostname missing from PATH the
# module must still run, and say which.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
exec /usr/bin/python3 "$here/../tools/fabric/guards/ban_generated_by_attribution.py" "$@"
