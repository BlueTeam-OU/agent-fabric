#!/usr/bin/env bash
# policies/githooks/locale-carve-out.sh — do these paths fall, all of them,
# under one locale's translations: identities/roles/<role>/locale/<suffix>/?
# Sourced by pre-commit and by the CI authority check; sets `locale_role`
# and `locale_suffix` and returns 0 when they do, 1 otherwise (any other
# path, two roles, two suffixes, a path deeper than the locale directory,
# or no path at all).
# For a merge in progress (a holder folding main into its translation
# branch), the paths to judge are what the result adds over the merged-in
# side — the branch's own content — not the union the index shows: the ge
# holder found a translation branch could never take main in once main
# had moved (2026-09-18).
locale_carve_out_paths() {
    local merge_head; merge_head="$(git rev-parse -q --verify MERGE_HEAD 2>/dev/null)" || merge_head=""
    if [[ -n "$merge_head" ]]; then
        git diff --cached --no-renames --name-only --diff-filter=ACDMRT "$merge_head" 2>/dev/null
    else
        git diff --cached --no-renames --name-only --diff-filter=ACDMRT 2>/dev/null
    fi
}
locale_carve_out_role() {
    locale_role=""; locale_suffix=""
    (( $# )) || return 1
    local p role suffix
    for p in "$@"; do
        [[ "$p" =~ ^identities/roles/([a-z][a-z0-9-]*)/locale/([a-z][a-z0-9-]*)/[^/]+$ ]] || return 1
        role="${BASH_REMATCH[1]}"; suffix="${BASH_REMATCH[2]}"
        if [[ -z "$locale_role" ]]; then locale_role="$role"; locale_suffix="$suffix"
        elif [[ "$role" != "$locale_role" || "$suffix" != "$locale_suffix" ]]; then locale_role=""; locale_suffix=""; return 1
        fi
    done
    return 0
}
