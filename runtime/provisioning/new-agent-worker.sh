#!/usr/bin/env bash
# runtime/provisioning/new-agent-worker.sh — the host half of new-agent.sh:
# what touches THIS machine (the account, its home, the installers, the host
# keys, the clones, bootstrap, the binding, the toolchain), run on the host
# the account is placed on, through runtime/hostexec/hostexec; it knows
# nothing of the account's secrets (ADR-038). The work, its contract and
# every reason for it are in tools/fabric/provisioning/worker.py (ADR-040,
# off shell).
#   new-agent-worker.sh prepare <login> (<role> | --human) [--claude V] [--dry-run]
#   new-agent-worker.sh finish <login> (<role> | --human) [--clone <id>=<remote>]... [--claude-account <slug>=<fp12> | --no-claude-account] [--signing-key-next] [--dry-run]
#   new-agent-worker.sh host-check <login>   hostname -s, then whether the account exists
#
# Why this entry stays bash: it is run on a FAR host through the host
# executor, where the fleet's pinned Python may not be installed yet, and then
# the operator must be told how to install it, from an executable that does not
# need it (the same reason runtime/provisioning/new-agent.sh stays).
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
PY=/usr/local/bin/fabric-python
[[ -x "$PY" ]] || { echo "new-agent: the fleet's pinned Python is not installed at $PY on $(hostname -s); as root: /usr/bin/python3 $ROOT/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$PY" -I "$ROOT/tools/fabric/provisioning/worker.py" "$@"
