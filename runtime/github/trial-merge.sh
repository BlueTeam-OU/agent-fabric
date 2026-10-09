#!/usr/bin/env bash
# runtime/github/trial-merge.sh — do these branches combine? The path is the
# contract, but DEPRECATED — use `fabric-pr trial-merge` (agents' procedures may still name it); the
# work, its rules and every reason for them are in
# tools/fabric/github/trial_merge.py (ADR-040 §5 rule 4). Bash builtins
# only, to find it: with git or hostname missing from PATH the module must
# still run, and say which.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# Deprecated (ADR-040 §5 rule 7): the command is `fabric-pr trial-merge`; this path stays
# for callers outside the checkout that still name it.
echo "deprecated: use fabric-pr trial-merge" >&2
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "trial-merge.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/../../tools/fabric/github/trial_merge.py" "$@"
