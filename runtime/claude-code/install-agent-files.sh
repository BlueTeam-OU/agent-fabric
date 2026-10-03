#!/usr/bin/env bash
# runtime/claude-code/install-agent-files.sh — install this account's
# capability-class agent files (and the locale worker on a language-culture
# login). The path is the contract (the launcher, bootstrap.sh and
# bin/fabric-model run it); the work, its contract and every reason for it
# are in tools/fabric/install_agent_files.py (ADR-040 §5 rule 4).
#
#   runtime/claude-code/install-agent-files.sh [--provider openrouter|anthropic] [--dry-run]
#
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
# The module is found by absolute path from this file, since a relative $0
# names nothing after the relaunch changes directory.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "install-agent-files: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../tools/fabric/install_agent_files.py" "$@"
