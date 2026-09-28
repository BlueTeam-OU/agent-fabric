#!/usr/bin/env bash
#
# policies/check_charter_authority.sh
#
# A role's DEFINITION is fabric-coordinator's to change: `identities/roles/*/
# charter.md` and `brief.md`, the catalogue `identities/roles/catalog.json`, the
# per-project binding rules `.agent-fabric/taxonomy.json` (this repository's own; a
# managed project's is under the .agent-fabric/ guard), the routing policy
# `routing/policies/*` and `policies/authority.json` itself. This fails
# when one of those changes on a branch that is not a fabric-coordinator
# branch.
#
# AUTHORITY BELONGS TO THE ROLE, NOT TO THE ACCOUNT. The branch's second
# segment names the agent (Linux login) that opened it. The check asks
# whether that agent is a recognised holder of fabric-coordinator: named
# in policies/authority.json, or named FOR the role by the provisioning
# convention (fabric-coordinator, fabric-coordinator-02). An account
# currently HOLDING some other role does not thereby own that role's
# definition — that is exactly the widening this tripwire exists to catch.
#
# WHY THIS EXISTS. Every distilled slice is generated -- the
# assembler writes it and lint.py rejects a hand-edit -- so a role's scope
# cannot drift by accident. `charter`, `brief` and `recall` are the classes
# lint.py exempts from `derived_from`, precisely because they are authored
# rather than distilled. That exemption is what makes charter.md (and the
# brief beside it, read to every session at launch) the one
# place a session can quietly widen its own remit, and it lints clean:
# lint checks PROVENANCE, and this is a question of AUTHORITY.
#
# WHAT THIS CANNOT DO, stated plainly so nobody mistakes it for a fence.
# Every session pushes as the same GitHub account, so there is no identity
# to check -- CODEOWNERS cannot tell one session from another here. All
# that is available is the branch name, which is self-declared. This is a
# TRIPWIRE: it stops the accident and the absent-minded edit, and it makes
# a deliberate change visible in review. A session that means to route
# around it can, by naming its branch differently, and nothing available
# in this repository would catch that.
#
# It also only enforces where a head branch is knowable. On a `merge_group`
# run the ref is the queue's synthetic branch, so the check reports and
# passes -- the `pull_request` run is where it bites, and that run is
# required before anything is queued.
#
# guards: identities/**
# guards: .agent-fabric/taxonomy.json
# guards: routing/policies/**
# guards: policies/**
#
# Exit codes:
#   0  no protected file changed, or the branch is fabric-coordinator's, or the
#      head branch is not knowable in this context
#   1  a protected file changed on another role's branch
#   0  also when no base ref is resolvable -- an environment that cannot
#      show a diff is not a violation, and failing there would block every
#      PR rather than the one changing a charter
#   2  invocation problem (cannot reach the repo root)

set -uo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || { echo "cannot cd to repo root" >&2; exit 2; }

# RESOLVING THE BASE IS THE HARD PART IN CI, not locally. `actions/checkout`
# defaults to depth 1 and, on a pull_request, checks out the MERGE ref -- so
# there is no `origin/main` and no `HEAD^1` to diff against. The first
# version assumed `origin/main` existed and exited 2 when it did not, which
# failed the build for an environment limitation rather than a violation.
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
    # Nothing local matched: fetch just the base tip. One shallow fetch, and
    # only on a pull_request where GITHUB_BASE_REF names the branch.
    if [[ -n "${GITHUB_BASE_REF:-}" ]] \
       && git fetch -q --depth=1 origin "$GITHUB_BASE_REF" 2>/dev/null; then
        printf 'FETCH_HEAD'; return 0
    fi
    return 1
}

BASE="$(resolve_base)" || {
    # NOT a build failure. This guard is a tripwire; an environment that
    # cannot show it a diff is not a violation, and failing here would
    # block every PR rather than the one changing a charter.
    echo "check_charter_authority: NOT ENFORCED — no base ref to diff"
    echo "against (shallow checkout with no GITHUB_BASE_REF). A charter"
    echo "change would pass unexamined here."
    exit 0
}

# GITHUB_HEAD_REF is set on pull_request and empty elsewhere; fall back to
# the local branch so this is runnable by hand before pushing.
BRANCH="${AGENT_FABRIC_CHARTER_BRANCH:-${GITHUB_HEAD_REF:-}}"
[[ -n "$BRANCH" ]] || BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"

# :(glob) so `*` stays inside one directory: git's default pathspec `*`
# crosses `/`, and matched identities/roles/<role>/locale/<suffix>/charter.md
# — a translation the locale's holder commits under the carve-out
# (policies/AUTHORITY.md), which the .agent-fabric/ tripwire and the hooks
# judge. Judged here too, every locale PR failed CI (#57 blind review F1).
mapfile -t changed < <(git diff --name-only "$BASE"...HEAD -- \
    ':(glob)identities/roles/*/charter.md' ':(glob)identities/roles/*/brief.md' 'identities/roles/catalog.json' \
    '.agent-fabric/taxonomy.json' 'projects/*/taxonomy.json' 'routing/policies/*' 'policies/authority.json' 2>/dev/null)

if (( ${#changed[@]} == 0 )); then
    echo "check_charter_authority: OK — no role definition changed."
    exit 0
fi

# The merge queue's synthetic ref is `gh-readonly-queue/<base>/pr-N-<sha>`,
# which HAS three segments -- so segment-counting alone reads its second
# one as the base branch and fails every charter change at the gate.
# Matched by name, explicitly, before anything is parsed out of it.
case "$BRANCH" in
    gh-readonly-queue/*|HEAD|"")
        echo "check_charter_authority: role definition(s) changed; not"
        echo "enforced on '${BRANCH:-detached HEAD}' — the pull_request run"
        echo "is where this is enforced, and it gates entry to the queue."
        printf '  %s\n' "${changed[@]}"
        exit 0 ;;
esac

# `<host>/<agent>/<type>/<desc>`: the second segment names the agent (the
# Linux login) that opened the branch, which is the only signal available.
agent="$(cut -d/ -f2 <<<"$BRANCH")"
if [[ "$BRANCH" != */*/* || -z "$agent" ]]; then
    echo "check_charter_authority: role definition(s) changed, but the head"
    echo "branch is not knowable here (${BRANCH:-none}) — the pull_request"
    echo "run is where this is enforced."
    printf '  %s\n' "${changed[@]}"
    exit 0
fi

# Holders: the committed list, or an account named for the role. Read from
# the BASE side of the diff, so a branch cannot add itself to the list in
# the same change it uses the list to justify.
holders="$(git show "$BASE:policies/authority.json" 2>/dev/null \
    | python3 -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
print(" ".join((d.get("role_definitions") or {}).get("holders") or []))' 2>/dev/null)"
owner_role="$(git show "$BASE:policies/authority.json" 2>/dev/null \
    | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["role_definitions"]["role"])
except Exception: print("fabric-coordinator")' 2>/dev/null)"
is_holder=0
for h in $holders; do [[ "$agent" == "$h" ]] && is_holder=1; done
[[ "$agent" == "$owner_role"* ]] && is_holder=1
if (( is_holder )); then
    echo "check_charter_authority: OK — ${#changed[@]} role definition(s)" \
         "changed on a $owner_role branch ($agent)."
    exit 0
fi

echo "FAIL: a role's DEFINITION changed on a branch owned by agent '$agent'." >&2
printf '       %s\n' "${changed[@]}" >&2
cat >&2 <<'MSG'

`identities/roles/*/charter.md`, the role catalogue, a project's
taxonomy, the routing policies and policies/authority.json say what a
role is and is not, where it applies, and who may change that. They are
fabric-coordinator's to change (policies/AUTHORITY.md) -- a role does not
redefine itself, and holding a role is not owning its definition.

Propose it instead: open a PR touching only the definition, say what the
role is being asked to take on or give up, and leave it for
fabric-coordinator. Do not self-approve on the grounds that you are the
only session that understands the surface; that is the argument this
exists to refuse.
MSG
exit 1
