#!/usr/bin/env bash
# projects/gzapp/integration/provisioning/host-check.sh — what a host must carry for an account that works on gzapp,
# beyond the fabric's own contract. The probe is host_check.py beside this file (ADR-040 §5 rule 1, Wave 9 batch 9);
# worker.py finish runs that directly, and this path stays for a person running the probe by hand.
#
# Pure bash on purpose: the probe finds podman and magick on the caller's PATH, which may hold nothing else.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
# The probe never stops a provisioning run, so a missing pin is said on stderr and the exit is 0.
[[ -x "$py" ]] || { echo "host-check gzapp: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 0; }
exec "$py" -I "${BASH_SOURCE[0]%/*}/host_check.py" "$@"
