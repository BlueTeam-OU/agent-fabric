#!/usr/bin/env bash
#
# policies/check_agent_fabric_dir_authority.sh
#
# `.agent-fabric/` in a repository is written by the fabric-coordinator
# ROLE. It holds the project's distilled knowledge (`memory/<role>/`,
# written by the drain) and nothing another role may edit by hand: a
# `backend-dev` session that changes a slice is asserting something about
# the system with no evidence behind it, outside the role that owns the
# corpus. This fails when a commit that changes `.agent-fabric/` does not
# declare that role.
#
# THE ROLE, NOT THE LOGIN. Which account committed is irrelevant; what
# matters is whether the session had the role BOUND when it committed.
# That binding is machine-local (runtime/identity.py), and the one place
# it can be checked for real is the keyboard: policies/githooks/pre-commit
# refuses the commit unless the binding holds the role, and commit-msg
# then writes what it verified into the message as a trailer:
#
#     Fabric-Role: fabric-coordinator
#
# This check reads that trailer on every commit the branch adds that
# touches `.agent-fabric/**`. In CI it is a TRIPWIRE: the trailer is
# text anyone can type, so it stops the accident — a session that never
# bound the role and never ran the hooks — and makes a deliberate change
# visible in review; it does not stop a session that means to route
# around it. The same limit check_charter_authority.sh states for the
# branch name. Merge commits are not examined (they carry no change of
# their own).
#
# RUNS IN ANY REPOSITORY. In agent-fabric ITSELF — recognised by
# policies/authority.json at the toplevel — EVERY commit the branch adds
# must declare the role: the control plane is read-only for every other
# role (CLAUDE.md, policies/AUTHORITY.md). In a managed project only the
# commits touching `.agent-fabric/**` must. The role name comes from
# policies/authority.json when this repository has one, else from
# $AGENT_FABRIC_ROOT/policies/authority.json, else it is
# fabric-coordinator.
#
# guards: .agent-fabric/**
# guards: ** (in agent-fabric itself)
#
# Exit codes:
#   0  nothing under .agent-fabric/ changed, or every such commit declares
#      the role, or no base ref is resolvable (not a violation)
#   1  a commit changed .agent-fabric/ without declaring the role
#   2  invocation problem (cannot reach the repo root)
set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "check_agent_fabric_dir_authority: not inside a git repository" >&2; exit 2; }

resolve_base() {
    local candidate
    for candidate in "${AGENT_FABRIC_CHARTER_BASE:-}" \
                     "origin/${GITHUB_BASE_REF:-}" "${GITHUB_BASE_REF:-}" \
                     origin/main main; do
        [[ -n "$candidate" && "$candidate" != "origin/" ]] || continue
        if git rev-parse --verify -q "$candidate" >/dev/null 2>&1; then
            printf '%s' "$candidate"; return 0
        fi
    done
    if [[ -n "${GITHUB_BASE_REF:-}" ]] \
       && git fetch -q --depth=1 origin "$GITHUB_BASE_REF" 2>/dev/null; then
        printf 'FETCH_HEAD'; return 0
    fi
    return 1
}

BASE="$(resolve_base)" || {
    echo "check_agent_fabric_dir_authority: NOT ENFORCED — no base ref to diff"
    echo "against (shallow checkout with no GITHUB_BASE_REF). A change under"
    echo ".agent-fabric/ would pass unexamined here."
    exit 0
}

owner_role=""
for f in policies/authority.json "${AGENT_FABRIC_ROOT:-$(pwd)/../agent-fabric}/policies/authority.json"; do
    [[ -f "$f" ]] || continue
    owner_role="$(python3 -c 'import json,sys
try: print(json.load(open(sys.argv[1]))["role_definitions"]["role"])
except Exception: print("")' "$f" 2>/dev/null)"
    [[ -n "$owner_role" ]] && break
done
[[ -n "$owner_role" ]] || owner_role="fabric-coordinator"

if [[ -f policies/authority.json ]]; then
    scope="agent-fabric itself"
    mapfile -t commits < <(git rev-list --no-merges "$BASE"..HEAD 2>/dev/null)
else
    scope=".agent-fabric/"
    mapfile -t commits < <(git rev-list --no-merges "$BASE"..HEAD -- '.agent-fabric/**' 2>/dev/null)
fi
if (( ${#commits[@]} == 0 )); then
    echo "check_agent_fabric_dir_authority: OK — no commit changes $scope."
    exit 0
fi

# The one carve-out (policies/AUTHORITY.md): a commit that changes nothing
# but identities/roles/<role>/locale/<suffix>/ may declare Fabric-Role:
# <role> — the holder of the role a locale translates writes its
# translations. The login is not visible here; the pre-commit hook held
# it to the suffix at the keyboard.
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/githooks/locale-carve-out.sh"
bad=()
for c in "${commits[@]}"; do
    declared="$(git log -1 --format=%B "$c" | git interpret-trailers --parse 2>/dev/null \
        | awk -F': *' 'tolower($1)=="fabric-role" {print $2}' | tail -1)"
    if [[ "$declared" != "$owner_role" ]]; then
        mapfile -t touched < <(git diff-tree --no-commit-id --name-only -r "$c" 2>/dev/null)
        if locale_carve_out_role "${touched[@]}" && [[ "$declared" == "$locale_role" ]]; then
            echo "check_agent_fabric_dir_authority: $(git log -1 --format='%h' "$c") changes only identities/roles/$locale_role/locale/$locale_suffix/, declaring Fabric-Role: $locale_role — the locale carve-out."
            continue
        fi
        bad+=("$(git log -1 --format='%h %s' "$c")  [Fabric-Role: ${declared:-none}]")
    fi
done

if (( ${#bad[@]} == 0 )); then
    echo "check_agent_fabric_dir_authority: OK — ${#commits[@]} commit(s) change $scope," \
         "each declaring Fabric-Role: $owner_role."
    exit 0
fi

echo "FAIL: $scope changed in ${#bad[@]} commit(s) that do not declare Fabric-Role: $owner_role." >&2
printf '       %s\n' "${bad[@]}" >&2
cat >&2 <<MSG

agent-fabric is read-only for every role but $owner_role — except a
locale's translations, identities/roles/<role>/locale/<suffix>/, which
the holder of <role> commits declaring its own role; in a managed
project, .agent-fabric/ (the project's distilled knowledge) is. A commit
there is made with that role bound (bin/fabric-role bind $owner_role,
from a login shell, then a relaunch) and the
agent-fabric git hooks installed (bootstrap.sh sets core.hooksPath): the
pre-commit hook checks the binding, the commit-msg hook records it as
the Fabric-Role trailer this check reads. The login that committed is
irrelevant. A wrong slice is corrected at the memory it was drained
from, or by a memory of the same class carrying merge_target with the
stale section's heading; the next drain puts it in place — never a hand
edit.
See agent-fabric policies/AUTHORITY.md.
MSG
exit 1
