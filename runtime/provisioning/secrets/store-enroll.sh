#!/usr/bin/env bash
# runtime/provisioning/secrets/store-enroll.sh — give an account its own
# key and its own encrypted store (agent-fabric ADR-038), run by its
# PARENT. The path is the contract (new-agent.sh and the README run it);
# the work, its contract, its help text and every reason for it are in
# tools/fabric/store_enroll.py (ADR-040 §5 rule 4).
#
#   store-enroll.sh <login>... [--host <id>] [--born-now] [--dry-run]
#   store-enroll.sh --self | --rename <old> <new> | --help
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "store-enroll: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../tools/fabric/store_enroll.py" "$@"
