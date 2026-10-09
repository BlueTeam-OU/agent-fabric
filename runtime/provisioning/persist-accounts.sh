#!/usr/bin/env bash
# runtime/provisioning/persist-accounts.sh — make the named accounts
# survive this host's reboot, the way this platform needs. The path is the
# contract (bin/fabric-host persist and the worker run it); the work, its
# contract and every reason for it are in
# tools/fabric/provisioning/persist_accounts.py (ADR-040, off shell).
#
#   persist-accounts.sh <login>...
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "persist-accounts: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../tools/fabric/provisioning/persist_accounts.py" "$@"
