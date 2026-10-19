#!/usr/bin/env bash
# runtime/claude-code/hooks/statusline.sh — the Claude Code status line. The path is the contract (the
# settings files run it by path); the work, its contract and every reason for
# it are in tools/fabric/statusline.py (ADR-040 §5 rule 1, Wave 9 batch 7).
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
# A hook keeps the script's contract, exit 0: a non-zero status line is an error on every refresh. The line itself
# says the pin is missing, so the gap stays visible.
[[ -x "$py" ]] || { echo "fabric-python missing: as root, /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install"; exit 0; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../tools/fabric/statusline.py" "$@"
