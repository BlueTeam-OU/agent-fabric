#!/usr/bin/env bash
# Install moveto from this directory to /usr/local. Needs root.
#
#     sudo runtime/provisioning/moveto/install.sh
#
# This directory is the SOURCE; /usr/local holds a copy. The work, its
# manifest and every reason for it are in
# tools/fabric/provisioning/install_moveto.py (ADR-040, off shell).
# $MOVETO_PREFIX overrides /usr/local for a test.
#
# POSIX sh on purpose: the suites run it as `sh install.sh`, as they did the
# script this replaced. The pinned Python (runtime/python.json) when the host
# has it; root may run this before it is installed, and the host's python3
# (no older than the floor, ADR-040 rule 1) does it then.
here=$(cd "$(dirname "$0")" && pwd)
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[ -x "$py" ] || py=python3
exec "$py" -I "$here/../../../tools/fabric/provisioning/install_moveto.py" "$@"
