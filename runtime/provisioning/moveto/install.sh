#!/usr/bin/env bash
# Install moveto from this directory to /usr/local. Needs root.
#
#     sudo runtime/provisioning/moveto/install.sh
#
# This directory is the SOURCE; /usr/local holds a copy. The work, its
# manifest and every reason for it are in
# tools/fabric/provisioning/install_moveto.py (ADR-040, off shell).
# $MOVETO_PREFIX overrides /usr/local for a test.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || py=python3   # root may run this before the pin is installed
exec "$py" -I "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../../tools/fabric/provisioning/install_moveto.py" "$@"
