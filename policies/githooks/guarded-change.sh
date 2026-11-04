#!/usr/bin/env bash
# policies/githooks/guarded-change.sh — a sourced shim (ADR-040 §5 rule 4): `guarded_change <fabric root>` sets
# `guarded_what` (a label) and `guarded` (the staged paths under guard, empty when nothing is). The decision, and every
# reason for it, is `guarded_change` in tools/fabric/guards/commit_hooks.py; the hooks no longer source this file, the
# oracle (tests/test_githook_guarded_change.py) does. It fails the call, never its caller.
_gc_py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
_gc_mod="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../tools/fabric/guards/commit_hooks.py"
guarded_change() {
    local out; out="$("$_gc_py" "$_gc_mod" guarded "$1")" || { echo "guarded_change: the fleet's pinned Python is not usable at $_gc_py" >&2; return 1; }
    guarded_what="${out%%$'\n'*}"; mapfile -t guarded < <(printf '%s\n' "$out" | sed 1d)
}
