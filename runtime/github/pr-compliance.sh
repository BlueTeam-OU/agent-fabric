#!/usr/bin/env bash
# runtime/github/pr-compliance.sh — the Actions-minute compliance measures
# over a window of merged pull requests. The path is the contract, but DEPRECATED — use `fabric-pr compliance` (the
# managed projects' tools/gh/pr-compliance.sh will forward here; until then
# each still runs its own copy); the work, its rules and every reason for
# them are in tools/fabric/github/pr_compliance.py (ADR-040 §5 rule 4).
# Bash builtins only, to find it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# Deprecated (ADR-040 §5 rule 7): the command is `fabric-pr compliance`; this path stays
# until the managed projects' forwarders are off it.
echo "deprecated: use fabric-pr compliance" >&2
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "pr-compliance.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/../../tools/fabric/github/pr_compliance.py" "$@"
