#!/usr/bin/env bash
# runtime/provisioning/rename-working-copy.sh — move an account's working
# copy and carry its Claude Code history with it. Host tooling, run by the
# coordinator with sudo.
#
#   rename-working-copy.sh <login> <old-name> <new-name> [--dry-run]
#
# The path is the contract (bin/fabric-host rename runs it there); the work,
# its contract and every reason for it are in
# tools/fabric/provisioning/rename_working_copy.py (ADR-040, off shell).
# The fleet's pinned Python (runtime/python.json), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "rename: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../tools/fabric/provisioning/rename_working_copy.py" "$@"
