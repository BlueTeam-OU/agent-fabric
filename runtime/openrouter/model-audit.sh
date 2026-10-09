#!/usr/bin/env bash
# runtime/openrouter/model-audit.sh — which model is THIS session actually
# running on, and what would each alias resolve to? The path is the contract
# (the README and sessions run it); the work, its contract and every reason
# for it are in tools/fabric/model_audit.py (ADR-040 §5 rule 4).
#
#   runtime/openrouter/model-audit.sh
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "model-audit: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../tools/fabric/model_audit.py" "$@"
