#!/usr/bin/env bash
# tools/fabric/query.sh — ask the corpus what it knows about an artifact.
# The path is the contract; the work, its rules and every reason for them
# are in tools/fabric/query.py (ADR-040 §5 rule 4), tested by
# tests/test_query_cli.py and tests/test_query.py. Bash builtins only, to find it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "query.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/query.py" "$@"
