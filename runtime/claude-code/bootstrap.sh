#!/usr/bin/env bash
# runtime/claude-code/bootstrap.sh — make agent-fabric's workspace
# instructions available to a Claude Code session launched from the parent
# projects/ directory, for THIS account. The path is the contract (new-agent's
# worker, the control agent's `upgrade fabric` and moveto's enter run it);
# the work, its contract and every reason for it are in
# tools/fabric/bootstrap.py (ADR-040 §5 rule 4).
#
#   runtime/claude-code/bootstrap.sh [--projects DIR] [--dry-run]
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
# The module is found by absolute path from this file: the callers run it
# by its path from wherever they are.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "bootstrap: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../tools/fabric/bootstrap.py" "$@"
