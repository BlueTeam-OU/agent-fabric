#!/usr/bin/env bash
# runtime/github/scan-semantic-collisions.sh — the numbering collisions a
# textually-clean merge hides. The path is the contract (the managed
# projects' tools/checks/scan_semantic_collisions.sh will forward here;
# until then each still runs its own copy); the work, its rules and every
# reason for them are in tools/fabric/github/semantic_collisions.py
# (ADR-040 §5 rule 4).
# Bash builtins only, to find it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "scan-semantic-collisions.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/../../tools/fabric/github/semantic_collisions.py" "$@"
