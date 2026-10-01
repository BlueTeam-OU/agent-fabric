#!/usr/bin/env bash
# tools/fabric/query.sh — ask the corpus what it knows about an artifact.
# The path is the contract; the work, its rules and every reason for them
# are in tools/fabric/query.py (ADR-040 §5 rule 4), tested by
# tests/test_query_cli.py and tests/test_query.py. Bash builtins only, to find it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
exec /usr/bin/python3 "$here/query.py" "$@"
