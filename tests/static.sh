#!/usr/bin/env bash
# tests/static.sh — forwards to tests/static.py, which holds the checks (its header is the contract).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$ROOT/tests/static.py" "$@"
