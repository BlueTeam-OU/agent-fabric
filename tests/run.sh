#!/usr/bin/env bash
# tests/run.sh — forwards to tests/run.py, which holds the run (its header is the contract). The name is kept so that
# CI, the docs and every habit keep working, and the variable makes the run call itself by it: its last line stays
# `tests/run.sh: all suites passed`.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_FABRIC_RUNNER=tests/run.sh exec python3 "$ROOT/tests/run.py" "$@"
