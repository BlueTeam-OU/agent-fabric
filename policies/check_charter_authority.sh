#!/usr/bin/env bash
# policies/check_charter_authority.sh — a role's DEFINITION is fabric-coordinator's
# to change. The path is the contract (tests/run.sh and CI call it, and its
# oracle copies it); the work, its rules and every reason for them are in
# tools/fabric/guards/charter_authority.py (ADR-040 §5 rule 4). Bash builtins
# only, to find it: with git missing from PATH the module must still run,
# and say which. The repository root is handed over as the module's first
# argument: it is this file's parent, which is not the module's when the
# oracle runs a copy of this file in a scratch repository.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "check_charter_authority.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/../tools/fabric/guards/charter_authority.py" "$here/.." "$@"
