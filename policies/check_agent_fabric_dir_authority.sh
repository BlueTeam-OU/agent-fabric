#!/usr/bin/env bash
# policies/check_agent_fabric_dir_authority.sh — `.agent-fabric/` is written by
# the fabric-coordinator ROLE. The path is the contract (tests/run.sh and CI
# call it); the work, its rules and every reason for them are in
# tools/fabric/guards/agent_fabric_dir_authority.py (ADR-040 §5 rule 4).
# Bash builtins only, to find it: with git missing from PATH the module must
# still run, and say which.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
exec /usr/bin/python3 "$here/../tools/fabric/guards/agent_fabric_dir_authority.py" "$@"
