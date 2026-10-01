#!/usr/bin/env bash
# policies/check_agent_fabric_dir_authority.sh — `.agent-fabric/` is written by
# the fabric-coordinator ROLE. The path is the contract (tests/run.sh and CI
# call it); the work, its rules and every reason for them are in
# tools/fabric/guards/agent_fabric_dir_authority.py (ADR-040 §5 rule 4).
# Bash builtins only, to find it: with git missing from PATH the module must
# still run, and say which.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "check_agent_fabric_dir_authority.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/../tools/fabric/guards/agent_fabric_dir_authority.py" "$@"
