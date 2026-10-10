#!/usr/bin/env bash
# policies/run_suite.sh — a forwarder, kept for any caller that names this
# path. The fabric's one run_suite is tools/fabric/github/run_suite.py
# (ported in #116; runtime/github/run-suite.sh is its bash path, under the
# same pinned interpreter): this copy was a second implementation of the
# same contract and would drift from it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "run_suite.sh: the fleet's pinned Python is not installed at $py" >&2; exit 127; }
exec "$py" "$here/../tools/fabric/github/run_suite.py" "$@"
