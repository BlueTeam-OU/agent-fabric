#!/usr/bin/env bash
# tools/fabric/github-repo-settings.sh — reapply this repository's GitHub-side
# settings (docs/adr/ADR-019-work-arrives-as-pull-requests.md §6). The path
# is the contract (ADR-019 names it); the work, its rules and every reason
# for them are in tools/fabric/github/repo_settings.py (ADR-040 Wave 1).
#
#   tools/fabric/github-repo-settings.sh [owner/repo]     # default: gzapi-org/agent-fabric
#   tools/fabric/github-repo-settings.sh --show [owner/repo]
here="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "github-repo-settings: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" "$here/github/repo_settings.py" "$@"
