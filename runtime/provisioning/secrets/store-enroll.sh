#!/usr/bin/env bash
# runtime/provisioning/secrets/store-enroll.sh — give an account its own
# key and its own encrypted store (agent-fabric ADR-038), run by its
# PARENT. Kept for one release so old callers keep working (ADR-040 §5 rule 7);
# the work, its contract, its help text and every reason for it are in
# tools/fabric/store_enroll.py (ADR-040 §5 rule 4).
#
#   store-enroll.sh <login>... [--host <id>] [--role <slug>] [--born-now] [--dry-run]
#   store-enroll.sh --self | --rename <old> <new> | --describe <login> [--role <slug>] | --help
#
# Retiring (ADR-040 §5 rule 7): the module is the entry, and it finds the
# fleet's pinned Python itself (or prints the install command, exit 127).
here="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../tools/fabric"
echo "store-enroll.sh is retired and goes in the next release; run: python3 $here/store_enroll.py" >&2
exec python3 "$here/store_enroll.py" "$@"
