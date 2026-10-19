#!/usr/bin/env bash
# policies/githooks/locale-carve-out.sh — a sourced shim (ADR-040 §5 rule 4): `locale_carve_out_paths` prints the staged
# paths to judge; `locale_carve_out_role PATH...` returns 0 and sets `locale_role` and `locale_suffix` when every path is
# a file of ONE locale's translations, 1 otherwise. The decision is in tools/fabric/guards/commit_hooks.py; the hooks no
# longer source this file, the oracle (tests/test_githook_locale_carve_out.py) does. It fails the call, never its caller.
_lc_py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
_lc_mod="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../tools/fabric/guards/commit_hooks.py"
locale_carve_out_paths() { "$_lc_py" "$_lc_mod" locale-paths; }
locale_carve_out_role() {
    local out rc; out="$("$_lc_py" "$_lc_mod" locale-role "$@")"; rc=$?
    IFS='|' read -r locale_role locale_suffix <<<"$out"
    return $rc
}
