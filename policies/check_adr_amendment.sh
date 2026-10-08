#!/usr/bin/env bash
# policies/check_adr_amendment.sh — RETIRING (agent-fabric ADR-040 rule 7):
# the check is `fabric-adr range-check`, which chooses the range itself
# (the GitHub event's base..head, else AGENT_FABRIC_ADR_BASE,
# origin/<GITHUB_BASE_REF>, origin/main or main, ..HEAD). This path says so
# and runs it, for one release, then goes.
set -uo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
echo "check_adr_amendment.sh is retiring: run fabric-adr range-check" >&2
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "check_adr_amendment.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/tools/fabric/adr.py" range-check "$@"
