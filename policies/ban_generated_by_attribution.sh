#!/usr/bin/env bash
# policies/ban_generated_by_attribution.sh — ban machine attribution from the
# commits a branch adds and from the pull-request description. The path is
# the contract (ci.yml and tests/run.sh name it); the work, its rules and
# every reason for them are in
# tools/fabric/guards/ban_generated_by_attribution.py (ADR-040 §5 rule 4).
# Bash builtins only, to find it: with git or hostname missing from PATH the
# module must still run, and say which.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "ban_generated_by_attribution.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/../tools/fabric/guards/ban_generated_by_attribution.py" "$@"
