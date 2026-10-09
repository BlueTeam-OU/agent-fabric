#!/usr/bin/env bash
# runtime/github/owed-supply.sh — every supply branch nobody has folded
# yet, and every open pull request still awaiting supply. The path is the
# contract (the managed projects' tools/gh/owed-supply.sh will forward
# here; until then each still runs its own copy); the work, its rules
# and every reason for them are in tools/fabric/github/owed_supply.py
# (ADR-040 §5 rule 4). Bash builtins only, to find it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# Deprecated (ADR-040 §5 rule 7): the command is `fabric-pr owed-supply`; this path stays
# for callers outside the checkout that still name it.
echo "deprecated: use fabric-pr owed-supply" >&2
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "owed-supply.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/../../tools/fabric/github/owed_supply.py" "$@"
