#!/usr/bin/env bash
# runtime/provisioning/new-agent.sh — give a role its own account on a
# host. The path is the contract (the runbook and the README run it); the
# work, its contract, its help text and every reason for it are in
# tools/fabric/new_agent.py (ADR-040 §5 rule 4); the host half is
# runtime/provisioning/new-agent-worker.sh.
#
#   runtime/provisioning/new-agent.sh <login> <role> [--host <id>] [--project <id>]... [--claude VERSION|stable|latest] [--dry-run]
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "new-agent: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../tools/fabric/new_agent.py" "$@"
