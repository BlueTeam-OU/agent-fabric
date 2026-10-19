#!/usr/bin/env bash
# runtime/claude-code/hooks/plan-hold.sh — the hook that holds this account's GZCoord inbox while a session plans. The path is the contract (the
# settings files run it by path); the work, its contract and every reason for
# it are in tools/fabric/plan_hold.py (ADR-040 §5 rule 1, Wave 9 batch 7).
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "plan-hold: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../tools/fabric/plan_hold.py" "$@"
