#!/usr/bin/env bash
#
# policies/test_check_agent_fabric_dir_authority.sh
#
# Self-test for check_agent_fabric_dir_authority.sh, on a throwaway git
# repository: the guard's whole input is the COMMITS a branch adds.
#
# Exit codes:
#   0  all assertions passed
#   1  one or more assertions failed
set -uo pipefail
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/check_agent_fabric_dir_authority.sh"
[[ -f "$UNDER_TEST" ]] || { echo "test: not found: $UNDER_TEST" >&2; exit 1; }
failures=0
SANDBOX=""
cleanup() { [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"; }
trap cleanup EXIT
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1" >&2; printf '%s\n' "${2:-}" | sed 's/^/      /' >&2; failures=$((failures+1)); }

# A managed-project repo with .agent-fabric/memory/<role>/ and a slice.
new_repo() {
  [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
  SANDBOX="$(mktemp -d)"
  mkdir -p "$SANDBOX/.agent-fabric/memory/backend-dev" "$SANDBOX/src"
  printf 'slice\n' > "$SANDBOX/.agent-fabric/memory/backend-dev/workflow.md"
  printf 'code\n' > "$SANDBOX/src/a.txt"
  git -C "$SANDBOX" init -q
  git -C "$SANDBOX" config user.email t@e; git -C "$SANDBOX" config user.name t
  # The account's signing (a gpg key, a timestamp that needs the network)
  # is not what this suite tests; a signer that fails made a case vacuous.
  git -C "$SANDBOX" config commit.gpgsign false
  git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -qm base
  git -C "$SANDBOX" branch -q base-ref
  git -C "$SANDBOX" branch -q -M sandbox-head
}
commit_change() {  # $1 = path; $2 = full message (optional)
  mkdir -p "$SANDBOX/$(dirname "$1")"
  printf 'changed %s\n' "$RANDOM" >> "$SANDBOX/$1"
  git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -q -m "${2:-touch $1}"
}
run_guard() {
  ( cd "$SANDBOX" && AGENT_FABRIC_ROOT=/nonexistent AGENT_FABRIC_CHARTER_BASE=base-ref GITHUB_BASE_REF= bash "$UNDER_TEST" 2>&1 )
}
rc_of() { run_guard >/dev/null; echo $?; }
DECLARED=$'drain\n\nFabric-Role: fabric-coordinator'

echo "nothing under .agent-fabric/ changed: passes"
new_repo; commit_change src/a.txt
[[ "$(rc_of)" == 0 ]] && pass "a code change passes, trailer or not" || fail "code change refused"

echo "a change under .agent-fabric/ must declare the role"
new_repo; commit_change .agent-fabric/memory/backend-dev/workflow.md
[[ "$(rc_of)" == 1 ]] && pass "no trailer: refused" || fail "undeclared change admitted"
out="$(run_guard)"
grep -q "do not declare Fabric-Role: fabric-coordinator" <<<"$out" && pass "the refusal names the missing trailer" || fail "refusal wording" "$out"
grep -q "\[Fabric-Role: none\]" <<<"$out" && pass "…and lists the commit with what it declared" || fail "commit not listed" "$out"
grep -q "irrelevant" <<<"$out" && pass "…and says the login is not the question" || fail "no role/login sentence" "$out"
grep -q "merge_target" <<<"$out" && ! grep -qi "raise it" <<<"$out" && pass "…and gives the slice correction, not a raise" || fail "slice wording" "$out"
new_repo; commit_change .agent-fabric/memory/backend-dev/workflow.md $'drain\n\nFabric-Role: backend-dev'
[[ "$(rc_of)" == 1 ]] && pass "a trailer naming another role: refused" || fail "wrong role admitted"
new_repo; commit_change .agent-fabric/memory/backend-dev/workflow.md "$DECLARED"
[[ "$(rc_of)" == 0 ]] && pass "Fabric-Role: fabric-coordinator: allowed" || fail "declared change refused" "$(run_guard)"
new_repo; commit_change .agent-fabric/memory/backend-dev/workflow.md $'drain\n\nfabric-role: Fabric-Coordinator'
[[ "$(rc_of)" == 1 ]] && pass "the role value is exact (case matters in a role id)" || fail "case-mangled role admitted"

echo "every commit that touches it is examined, not only the tip"
new_repo
commit_change .agent-fabric/memory/backend-dev/workflow.md "$DECLARED"
commit_change .agent-fabric/memory/backend-dev/workflow.md
commit_change src/a.txt "$DECLARED"
[[ "$(rc_of)" == 1 ]] && pass "an undeclared commit in the middle is caught" || fail "middle commit missed"
out="$(run_guard)"; [[ "$(grep -c '\[Fabric-Role: none\]' <<<"$out")" == 1 ]] && pass "exactly the offending commit is listed" || fail "listing" "$out"

echo "in agent-fabric itself (policies/authority.json present) EVERY commit must declare the role"
new_repo; mkdir -p "$SANDBOX/policies"
printf '{"role_definitions":{"role":"corpus-keeper","holders":[]}}\n' > "$SANDBOX/policies/authority.json"
git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -qm "policy"; git -C "$SANDBOX" branch -f base-ref
commit_change src/a.txt
[[ "$(rc_of)" == 1 ]] && pass "a code change with no trailer is refused in the fabric" || fail "fabric code change admitted"
grep -q "agent-fabric itself changed" <<<"$(run_guard)" && pass "…and the refusal says the whole repository is guarded" || fail "scope wording" "$(run_guard)"
new_repo; mkdir -p "$SANDBOX/policies"
printf '{"role_definitions":{"role":"corpus-keeper","holders":[]}}\n' > "$SANDBOX/policies/authority.json"
git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -qm "policy"; git -C "$SANDBOX" branch -f base-ref
commit_change src/a.txt $'code\n\nFabric-Role: corpus-keeper'
[[ "$(rc_of)" == 0 ]] && pass "a code change declaring the owning role passes" || fail "declared fabric change refused" "$(run_guard)"
commit_change .agent-fabric/memory/backend-dev/workflow.md "$DECLARED"
[[ "$(rc_of)" == 1 ]] && pass "fabric-coordinator is refused where the owning role is corpus-keeper (role name read from authority.json)" || fail "role name not read"

echo "the one carve-out: a commit changing only identities/roles/<role>/locale/<suffix>/ may declare Fabric-Role: <role>"
new_repo; mkdir -p "$SANDBOX/policies"; printf '{"role_definitions":{"role":"fabric-coordinator","holders":[]}}\n' > "$SANDBOX/policies/authority.json"
git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -qm 'authority' ; git -C "$SANDBOX" branch -f base-ref
commit_change identities/roles/language-culture/locale/ge/harness.md $'ge harness\n\nFabric-Role: language-culture'
[[ "$(rc_of)" == 0 ]] && grep -q "the locale carve-out" <<<"$(run_guard)" && pass "a locale commit declaring the role it translates: admitted, and said" || fail "carve-out refused" "$(run_guard)"
commit_change identities/roles/language-culture/locale/ge/team.md $'ge team\n\nFabric-Role: backend-dev'
[[ "$(rc_of)" == 1 ]] && pass "a locale commit declaring another role: refused" || fail "wrong role admitted"
new_repo; mkdir -p "$SANDBOX/policies"; printf '{"role_definitions":{"role":"fabric-coordinator","holders":[]}}\n' > "$SANDBOX/policies/authority.json"
git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -qm 'authority'; git -C "$SANDBOX" branch -f base-ref
mkdir -p "$SANDBOX/identities/roles/language-culture/locale/ge"; printf 'x\n' > "$SANDBOX/identities/roles/language-culture/locale/ge/team.md"; printf 'y\n' >> "$SANDBOX/src/a.txt"
git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -q -m $'locale and code\n\nFabric-Role: language-culture'
[[ "$(rc_of)" == 1 ]] && pass "a locale file beside a code change, declaring the locale's role: refused" || fail "mixed commit admitted"
commit_change identities/roles/language-culture/charter.md $'charter\n\nFabric-Role: language-culture'
[[ "$(rc_of)" == 1 ]] && pass "the English charter is not the locale: refused" || fail "charter admitted"

echo "unresolvable base: not enforced, not a failure"
new_repo; commit_change .agent-fabric/memory/backend-dev/workflow.md
rc="$( ( cd "$SANDBOX" && AGENT_FABRIC_CHARTER_BASE=no-such-ref GITHUB_BASE_REF= bash "$UNDER_TEST" >/dev/null 2>&1 ); echo $? )"
[[ "$rc" == 0 ]] && pass "no base ref: reports and passes" || fail "unresolvable base failed the build"

echo
if (( failures )); then echo "test_check_agent_fabric_dir_authority: $failures assertion(s) FAILED"; exit 1; fi
echo "all assertions passed"
