#!/usr/bin/env bash
# runtime/claude-code/hooks/model-fallback-note.sh — the PostModelSwitch hook that tells a session its model fell back. The path is the contract (the
# settings files run it by path); the work, its contract and every reason for
# it are in tools/fabric/model_fallback_note.py (ADR-040 §5 rule 1, Wave 9 batch 6).
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
# A note, not a guard: a hook that cannot run is "no note" and exit 0, as this script was without jq (a non-zero hook is an
# error notice on every switch). It says the missing pin on stderr and does nothing.
[[ -x "$py" ]] || { echo "model-fallback-note: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 0; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../tools/fabric/model_fallback_note.py" "$@"
