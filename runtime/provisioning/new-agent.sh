#!/usr/bin/env bash
# runtime/provisioning/new-agent.sh — give a role its own account on a
# host. The path is the contract (the runbook and the README run it); the
# work, its contract, its help text and every reason for it are in
# tools/fabric/new_agent.py (ADR-040 §5 rule 4); the host half is
# runtime/provisioning/new-agent-worker.sh.
#
#   runtime/provisioning/new-agent.sh <login> <role> (--claude-account <slug> | --no-claude-account)
#       [--host <id>] [--project <id>]... [--claude VERSION|stable|latest] [--surname <Surname>] [--dry-run]
#   runtime/provisioning/new-agent.sh --signing-key-only <login>     # step 11 alone, at a terminal
#
# Retiring (ADR-040 §5 rule 7): the module is the entry, and it finds the
# fleet's pinned Python itself (or prints the install command, exit 127).
here="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../tools/fabric"
echo "new-agent.sh is retired and goes in the next release; run: python3 $here/new_agent.py" >&2
exec python3 "$here/new_agent.py" "$@"
