#!/usr/bin/env bash
# runtime/github/arm.sh — arm auto-merge on a pull request behind the
# gates the project puts before the arming (its arm.json: the boundary
# paths and the classes). The path is the contract, but DEPRECATED — use `fabric-pr arm` (the managed projects'
# tools/gh/arm.sh forward here); the work, its rules and every reason
# for them are in tools/fabric/github/arm.py (ADR-040 §5 rule 4).
# Bash builtins only, to find it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# Deprecated (ADR-040 §5 rule 7): the command is `fabric-pr arm`; this path stays
# until the managed projects' forwarders are off it.
echo "deprecated: use fabric-pr arm" >&2
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "arm.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/../../tools/fabric/github/arm.py" "$@"
