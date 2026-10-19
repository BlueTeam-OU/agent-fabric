#!/usr/bin/env bash
# runtime/claude-code/hooks/tab-title.sh — the terminal tab title hook. The path is the contract (the
# settings files run it by path); the work, its contract and every reason for
# it are in tools/fabric/tab_title.py (ADR-040 §5 rule 1, Wave 9 batch 7).
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
# A hook keeps the script's contract, exit 0: a non-zero hook is an error notice on every call. The status line
# shows the missing pin; this one says it on stderr and does nothing.
[[ -x "$py" ]] || { echo "tab-title: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 0; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../tools/fabric/tab_title.py" "$@"
