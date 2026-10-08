#!/usr/bin/env bash
# runtime/github/check-workflows-lint.sh — every workflow through actionlint
# and zizmor at their pinned releases. The path is the contract (the managed
# projects' tools/checks/check_workflows_lint.sh will forward here; until
# then each still runs its own copy); the work, its rules and every reason
# for them are in tools/fabric/github/workflows_lint.py (ADR-040 §5 rule 4).
# Bash builtins only, to find it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "check-workflows-lint.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/../../tools/fabric/github/workflows_lint.py" "$@"
