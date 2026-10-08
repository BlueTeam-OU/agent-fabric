#!/usr/bin/env bash
# policies/run_suite.sh — a forwarder, kept for any caller that names this
# path. The fabric's one run_suite is runtime/github/run-suite.sh
# (tools/fabric/github/run_suite.py, ported in #116): this copy was a
# second implementation of the same contract and would drift from it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
exec "$here/../runtime/github/run-suite.sh" "$@"
