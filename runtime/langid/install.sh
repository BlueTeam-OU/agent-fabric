#!/usr/bin/env bash
# runtime/langid/install.sh — the language detector for THIS account. The
# path is the contract (bootstrap runs it by path); the work, its contract
# and every reason for it are in tools/fabric/langid_install.py (ADR-040
# §5 rule 4, Wave 9 batch 9).
#
#   runtime/langid/install.sh [--dry-run]
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "langid-install: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../tools/fabric/langid_install.py" "$@"
