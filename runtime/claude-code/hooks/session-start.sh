#!/usr/bin/env bash
# Claude Code SessionStart hook: a forwarder to session-start.py on the
# fleet's pinned Python (agent-fabric ADR-040 rule 4), which resolves the
# agent, records the working copy and project, exports AGENT_FABRIC_ROOT
# into the session's shell and prints one context line. Exit 0 always: a
# start hook never stands in a session's way.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
root="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../.." && pwd)"
[[ -x "$py" ]] || { echo "session-start: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 $root/tools/fabric/python_pin.py install" >&2; exit 0; }
AGENT_FABRIC_ROOT="${AGENT_FABRIC_ROOT:-$root}" "$py" "$root/runtime/claude-code/hooks/session-start.py"
exit 0
