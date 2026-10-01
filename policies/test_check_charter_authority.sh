#!/usr/bin/env bash
#
# policies/test_check_charter_authority.sh
#
# Self-test for check_charter_authority.sh.
#
# Built on a throwaway git repository, because the guard's whole input is
# a COMMITTED diff against a base ref. The first version of this test
# modified the working tree and asserted the guard fired; it did not, and
# could not — `git diff BASE...HEAD` never sees an uncommitted change. A
# positive control is the only reason that was caught.
#
# Exit codes:
#   0  all assertions passed
#   1  one or more assertions failed

set -uo pipefail

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/check_charter_authority.sh"
[[ -f "$UNDER_TEST" ]] || { echo "test: not found: $UNDER_TEST" >&2; exit 1; }

failures=0
SANDBOX=""
cleanup() { [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"; }
trap cleanup EXIT

pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1" >&2; printf '%s\n' "${2:-}" | sed 's/^/      /' >&2; failures=$((failures+1)); }

GUARD_MARKER="$(mktemp)"
command_not_found_handle() {
  echo "UNDEFINED COMMAND: $1" >> "$GUARD_MARKER"; return 127
}

# A repo with a base commit, the guard in place, and a charter to touch.
new_repo() {
  [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
  SANDBOX="$(mktemp -d)"
  mkdir -p "$SANDBOX/policies" "$SANDBOX/identities/roles/flutter-dev" "$SANDBOX/projects/demo" \
           "$SANDBOX/memory/projects/demo/flutter-dev"
  cp "$UNDER_TEST" "$SANDBOX/policies/"
  # The guard is a shim that finds its module beside it (ADR-040 §5 rule 4),
  # so the copy above needs the module copied too; the original bash ignores
  # these files. Kept out of the repository under test by info/exclude, below.
  mkdir -p "$SANDBOX/tools/fabric/guards"
  cp "$SCRIPT_DIR"/../tools/fabric/git.py "$SANDBOX/tools/fabric/"
  cp "$SCRIPT_DIR"/../tools/fabric/guards/*.py "$SANDBOX/tools/fabric/guards/"
  printf 'scope\n' > "$SANDBOX/identities/roles/flutter-dev/charter.md"
  printf '{"roles":[]}\n' > "$SANDBOX/identities/roles/catalog.json"
  printf '{"role_definitions":{"role":"fabric-coordinator","holders":["coord-01"]}}\n' > "$SANDBOX/policies/authority.json"
  printf '{"roles":[]}\n' > "$SANDBOX/projects/demo/taxonomy.json"
  printf 'other\n' > "$SANDBOX/memory/projects/demo/flutter-dev/workflow.md"
  git -C "$SANDBOX" init -q
  git -C "$SANDBOX" config user.email t@e; git -C "$SANDBOX" config user.name t
  printf 'tools/\n' >> "$SANDBOX/.git/info/exclude"
  git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -qm base
  git -C "$SANDBOX" branch -q base-ref
  # Renamed so there is no `main` for the guard to fall back to:
  # the unresolvable-base case below depends on its absence.
  git -C "$SANDBOX" branch -q -M sandbox-head
}

commit_change() {  # $1 = path, relative
  echo "changed" >> "$SANDBOX/$1"
  git -C "$SANDBOX" add -A
  git -C "$SANDBOX" commit -qm "change $1"
}

check() {  # $1 = branch label; echoes output, returns the guard's code
  ( cd "$SANDBOX" && AGENT_FABRIC_CHARTER_BASE=base-ref AGENT_FABRIC_CHARTER_BRANCH="$1" \
      bash policies/check_charter_authority.sh 2>&1 )
}
rc_of() { ( cd "$SANDBOX" && AGENT_FABRIC_CHARTER_BASE=base-ref AGENT_FABRIC_CHARTER_BRANCH="$1" \
      bash policies/check_charter_authority.sh >/dev/null 2>&1 ); echo $?; }

echo "a charter change by another role"
new_repo; commit_change "identities/roles/flutter-dev/charter.md"
rc="$(rc_of develop-qzapp/flutter-dev-01/feat/thing)"
[[ "$rc" == 1 ]] && pass "refused (exit 1)" || fail "refused (exit 1)" "exit $rc"
out="$(check develop-qzapp/flutter-dev-01/feat/thing)"
[[ "$out" == *"flutter-dev-01"* ]] && pass "names the branch owner" || fail "names the branch owner" "$out"
[[ "$out" == *"charter.md"* ]] && pass "names the file" || fail "names the file" "$out"
[[ "$out" == *"Propose it instead"* ]] && pass "says what to do instead" || fail "says what to do instead" "$out"

echo "the same change by a recognised holder of fabric-coordinator"
rc="$(rc_of develop-qzapp/coord-01/feat/x)"
[[ "$rc" == 0 ]] && pass "allowed for a listed holder (exit 0)" || fail "allowed for a listed holder (exit 0)" "exit $rc"
rc="$(rc_of develop-qzapp/fabric-coordinator-02/feat/x)"
[[ "$rc" == 0 ]] && pass "allowed for an account named for the role" || fail "allowed for an account named for the role" "exit $rc"

echo "architect-cto no longer owns role definitions"
rc="$(rc_of develop-qzapp/architect-cto-01/feat/x)"
[[ "$rc" == 1 ]] && pass "refused (exit 1)" || fail "refused (exit 1)" "exit $rc"

echo "a branch cannot add itself to the holders in the same change"
new_repo
python3 - "$SANDBOX/policies/authority.json" <<'PY2'
import json,sys
p=sys.argv[1]; d=json.load(open(p)); d["role_definitions"]["holders"].append("web-dev-01"); json.dump(d,open(p,"w"))
PY2
git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -qm "self-appoint"
rc="$(rc_of develop-qzapp/web-dev-01/feat/x)"
[[ "$rc" == 1 ]] && pass "the holders list is read from the base side" || fail "the holders list is read from the base side" "exit $rc"

echo "routing policy is protected too"
new_repo; mkdir -p "$SANDBOX/routing/policies"; printf '{}\n' > "$SANDBOX/routing/policies/review-grade.json"
git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -qm "add policy"; git -C "$SANDBOX" branch -f base-ref
commit_change "routing/policies/review-grade.json"
rc="$(rc_of develop-qzapp/backend-dev-02/feat/x)"
[[ "$rc" == 1 ]] && pass "refused" || fail "refused" "exit $rc"

echo "a locale holder's translation is the carve-out's, not this guard's"
new_repo; mkdir -p "$SANDBOX/identities/roles/language-culture/locale/ru"
printf 'устав\n' > "$SANDBOX/identities/roles/language-culture/locale/ru/charter.md"
printf 'бриф\n' > "$SANDBOX/identities/roles/language-culture/locale/ru/brief.md"
git -C "$SANDBOX" add -A; git -C "$SANDBOX" commit -qm "add locale"; git -C "$SANDBOX" branch -f base-ref
commit_change "identities/roles/language-culture/locale/ru/charter.md"
commit_change "identities/roles/language-culture/locale/ru/brief.md"
rc="$(rc_of develop-qzapp/language-culture-ru/fix/ru-locale)"
[[ "$rc" == 0 ]] && pass "a translated charter and brief pass (exit 0)" || fail "a translated charter and brief pass (exit 0)" "exit $rc"
commit_change "identities/roles/flutter-dev/charter.md"
rc="$(rc_of develop-qzapp/language-culture-ru/fix/ru-locale)"
[[ "$rc" == 1 ]] && pass "…but the same branch changing a role's own charter is refused" || fail "…own charter refused" "exit $rc"

echo "the catalogue is protected too"
new_repo; commit_change "identities/roles/catalog.json"
rc="$(rc_of develop-qzapp/web-dev-01/feat/x)"
[[ "$rc" == 1 ]] && pass "refused" || fail "refused" "exit $rc"

echo "a project's taxonomy (where roles apply) is protected too"
new_repo; commit_change "projects/demo/taxonomy.json"
rc="$(rc_of develop-qzapp/web-dev-01/feat/x)"
[[ "$rc" == 1 ]] && pass "refused" || fail "refused" "exit $rc"

echo "an agent HOLDING a role does not own its definition"
# The account is named for the role it was stood up as; holding flutter-dev
# and editing flutter-dev's charter is still not architect-cto's authority.
new_repo; commit_change "identities/roles/flutter-dev/charter.md"
rc="$(rc_of develop-qzapp/flutter-dev-02/feat/widen-my-remit)"
[[ "$rc" == 1 ]] && pass "refused for the role's own instance" || fail "refused for the role's own instance" "exit $rc"

echo "an ordinary slice is NOT protected"
# The control that keeps this from being a blanket ban on touching .roles/:
# every other file there is generated, and the drain rewrites them.
new_repo; commit_change "memory/projects/demo/flutter-dev/workflow.md"
rc="$(rc_of develop-qzapp/flutter-dev-01/feat/x)"
[[ "$rc" == 0 ]] && pass "a distilled slice may change on any branch" \
    || fail "a distilled slice may change on any branch" "exit $rc"

echo "nothing changed at all"
new_repo
rc="$(rc_of develop-qzapp/flutter-dev-01/feat/x)"
[[ "$rc" == 0 ]] && pass "passes" || fail "passes" "exit $rc"

echo "the merge queue's synthetic ref"
# It HAS three segments, so segment-counting reads its second as the base
# branch and fails every charter change at the gate. Matched by name.
new_repo; commit_change "identities/roles/flutter-dev/charter.md"
rc="$(rc_of gh-readonly-queue/main/pr-999-abc)"
[[ "$rc" == 0 ]] && pass "not enforced in the queue" || fail "not enforced in the queue" "exit $rc"
out="$(check gh-readonly-queue/main/pr-999-abc)"
[[ "$out" == *"the pull_request run"* ]] \
    && pass "says where it IS enforced" || fail "says where it IS enforced" "$out"

echo "no base ref is resolvable"
# The guard must NOT fail the build here. An environment that cannot show
# it a diff is not a violation, and exiting non-zero would block every PR
# rather than the one changing a charter -- which is exactly what the
# first version did in CI, where actions/checkout leaves no origin/main.
new_repo; commit_change "identities/roles/flutter-dev/charter.md"
rc="$( ( cd "$SANDBOX" && AGENT_FABRIC_CHARTER_BASE=no-such-ref GITHUB_BASE_REF= \
    AGENT_FABRIC_CHARTER_BRANCH=develop-qzapp/flutter-dev-01/feat/x \
    bash policies/check_charter_authority.sh >/dev/null 2>&1 ); echo $? )"
[[ "$rc" == 0 ]] && pass "passes rather than blocking every PR" \
    || fail "passes rather than blocking every PR" "exit $rc"
out="$( cd "$SANDBOX" && AGENT_FABRIC_CHARTER_BASE=no-such-ref GITHUB_BASE_REF= \
    AGENT_FABRIC_CHARTER_BRANCH=develop-qzapp/flutter-dev-01/feat/x \
    bash policies/check_charter_authority.sh 2>&1 )"
[[ "$out" == *"NOT ENFORCED"* ]] && pass "says it did not enforce" \
    || fail "says it did not enforce" "$out"

echo "a detached HEAD"
rc="$(rc_of HEAD)"
[[ "$rc" == 0 ]] && pass "reports rather than guessing" || fail "reports rather than guessing" "exit $rc"

if [[ -s "$GUARD_MARKER" ]]; then
  echo >&2; echo "UNDEFINED COMMANDS were called:" >&2
  sort -u "$GUARD_MARKER" | sed 's/^/  /' >&2; failures=$((failures+1))
fi
rm -f "$GUARD_MARKER"

echo
if [[ "$failures" -eq 0 ]]; then echo "all assertions passed"; exit 0; fi
echo "$failures assertion(s) failed" >&2; exit 1
