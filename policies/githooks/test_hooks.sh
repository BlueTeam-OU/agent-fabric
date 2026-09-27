#!/usr/bin/env bash
# policies/githooks/test_hooks.sh — the .agent-fabric/ fence at the keyboard.
#
# pre-commit refuses a commit staging anything under .agent-fabric/ unless
# the agent's runtime binding holds the fabric-coordinator role; commit-msg
# then records that role as the Fabric-Role trailer. The binding is read
# through runtime/identity.py, so a throwaway AGENT_FABRIC_STATE_DIR is the
# whole fixture. Exit 0 = all assertions passed.
set -uo pipefail
HOOKS="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
failures=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1" >&2; printf '%s\n' "${2:-}" | sed 's/^/      /' >&2; failures=$((failures+1)); }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
LOGIN="$(id -un)"

bind() {  # $1 = role or "" for none
  mkdir -p "$TMP/state/agents/$LOGIN"
  printf '{"agent":"%s","host":"%s","role":%s,"project":"demo","working_copy":null,"updated_at":"x"}\n' \
    "$LOGIN" "$(hostname -s)" "$( [[ -n "$1" ]] && printf '"%s"' "$1" || printf null )" > "$TMP/state/agents/$LOGIN/binding.json"
}
new_repo() {
  rm -rf "$TMP/repo"; mkdir -p "$TMP/repo/.agent-fabric/memory/backend-dev" "$TMP/repo/src"
  git -C "$TMP/repo" init -q
  git -C "$TMP/repo" config user.email t@e; git -C "$TMP/repo" config user.name t
  git -C "$TMP/repo" config core.hooksPath "$HOOKS"
  printf 'code\n' > "$TMP/repo/src/a.txt"; printf 'slice\n' > "$TMP/repo/.agent-fabric/memory/backend-dev/workflow.md"
  git -C "$TMP/repo" add -A; git -C "$TMP/repo" -c core.hooksPath=/dev/null commit -qm base
}
try_commit() {  # $1 = path to touch, $2 = message; prints rc
  printf 'more\n' >> "$TMP/repo/$1"; git -C "$TMP/repo" add -A
  ( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git commit -q -m "$2" >/dev/null 2>"$TMP/err" ); echo $?
}

echo "a commit outside .agent-fabric/ is untouched by the fence, and declares the role that made it"
bind backend-dev; new_repo
[[ "$(try_commit src/a.txt 'code')" == 0 ]] && pass "commits with any role" || fail "refused" "$(cat "$TMP/err")"
git -C "$TMP/repo" log -1 --format=%B | grep -q '^Fabric-Role: backend-dev$' && pass "…and declares Fabric-Role: backend-dev (every account commits under one author; the trailer names the lane)" || fail "no trailer on a code commit" "$(git -C "$TMP/repo" log -1 --format=%B)"
[[ "$(try_commit src/a.txt $'typed\n\nFabric-Role: architect-cto')" == 0 ]] && pass "a typed trailer on a code commit is left as typed (a claim, not the binding)" || fail "refused" "$(cat "$TMP/err")"
git -C "$TMP/repo" log -1 --format=%B | grep -c '^Fabric-Role:' | grep -q '^1$' && pass "…and not doubled" || fail "trailer doubled" "$(git -C "$TMP/repo" log -1 --format=%B)"
rm -f "$TMP/state/agents/"*/binding.json
[[ "$(try_commit src/a.txt 'unbound')" == 0 ]] && pass "no binding: the commit is admitted" || fail "refused without a binding" "$(cat "$TMP/err")"
git -C "$TMP/repo" log -1 --format=%B | grep -q 'Fabric-Role' && fail "a trailer with no binding to back it" || pass "…and declares nothing (a fact about the account, never a claim it cannot make)"

echo "a commit under .agent-fabric/ needs the role bound"
bind backend-dev; new_repo
[[ "$(try_commit .agent-fabric/memory/backend-dev/workflow.md 'hand edit')" == 1 ]] && pass "backend-dev bound: refused" || fail "hand edit committed"
grep -q "this agent's binding holds: backend-dev" "$TMP/err" && pass "the refusal says what is bound" || fail "wording" "$(cat "$TMP/err")"
bind ""; new_repo
[[ "$(try_commit .agent-fabric/memory/backend-dev/workflow.md 'hand edit')" == 1 ]] && pass "no role bound: refused" || fail "unbound commit admitted"
bind fabric-coordinator; new_repo
[[ "$(try_commit .agent-fabric/memory/backend-dev/workflow.md 'drain')" == 0 ]] && pass "fabric-coordinator bound: allowed" || fail "coordinator refused" "$(cat "$TMP/err")"
git -C "$TMP/repo" log -1 --format=%B | grep -q '^Fabric-Role: fabric-coordinator$' && pass "…and the commit declares Fabric-Role: fabric-coordinator" || fail "no trailer" "$(git -C "$TMP/repo" log -1 --format=%B)"

echo "the declaration is the fact the fence checked, never a paste"
bind backend-dev; new_repo
[[ "$(try_commit .agent-fabric/memory/backend-dev/workflow.md $'x\n\nFabric-Role: fabric-coordinator')" == 1 ]] && pass "a typed trailer does not substitute for the binding" || fail "pasted trailer admitted"

echo "in agent-fabric itself, every commit needs the role"
bind backend-dev; new_repo
mkdir -p "$TMP/repo/policies"; printf '{"role_definitions":{"role":"fabric-coordinator","holders":[]}}\n' > "$TMP/repo/policies/authority.json"
# The hooks recognise the fabric by their own location: point them at a copy living inside this repo.
mkdir -p "$TMP/repo/policies/githooks" "$TMP/repo/runtime"; cp "$HOOKS"/pre-commit "$HOOKS"/commit-msg "$HOOKS"/guarded-change.sh "$HOOKS"/locale-carve-out.sh "$TMP/repo/policies/githooks/"
cp "$HOOKS/../../runtime/identity.py" "$TMP/repo/runtime/"   # the hooks read the binding through their own fabric's resolver
git -C "$TMP/repo" config core.hooksPath "$TMP/repo/policies/githooks"
git -C "$TMP/repo" add -A; git -C "$TMP/repo" -c core.hooksPath=/dev/null commit -qm "hooks in place"
[[ "$(try_commit src/a.txt 'code')" == 1 ]] && pass "backend-dev bound: a code change in the fabric is refused" || fail "fabric code change committed" "$(cat "$TMP/err")"
grep -q "agent-fabric itself" "$TMP/err" && pass "the refusal names the whole repository" || fail "wording" "$(cat "$TMP/err")"
bind fabric-coordinator
[[ "$(try_commit src/a.txt 'code')" == 0 ]] && pass "fabric-coordinator bound: allowed" || fail "coordinator refused in fabric" "$(cat "$TMP/err")"
git -C "$TMP/repo" log -1 --format=%B | grep -q '^Fabric-Role: fabric-coordinator$' && pass "…and every fabric commit declares the role" || fail "no trailer on a fabric commit"

echo "in agent-fabric itself, a commit touching docs/adr/ leaves the decision records consistent"
mkdir -p "$TMP/repo/tools/fabric" "$TMP/repo/docs" "$TMP/repo/projects"
cp "$HOOKS/../../tools/fabric/adr.py" "$TMP/repo/tools/fabric/"; cp -r "$HOOKS/../../docs/adr" "$TMP/repo/docs/"; cp "$HOOKS/../../projects/registry.json" "$TMP/repo/projects/"
git -C "$TMP/repo" add -A; git -C "$TMP/repo" -c core.hooksPath=/dev/null commit -qm "records in place"
[[ "$(try_commit docs/adr/DIGEST.md 'a note in the digest')" == 0 ]] && pass "a consistent change to docs/adr/ commits" || fail "a consistent records change was refused" "$(cat "$TMP/err")"
[[ "$(try_commit docs/adr/index.json 'hand-edit the generated index')" == 1 ]] && grep -q "index.json: stale" "$TMP/err" && pass "a hand-edited generated index: refused, naming it" || fail "an inconsistent index was committed" "$(cat "$TMP/err")"
git -C "$TMP/repo" reset -q --hard
# The staged tree is what is checked: a consistent working tree does not
# cover a commit that leaves the regenerated index out of it.
sed -i 's/^# ADR-001 — Decision records$/# ADR-001 — Decision record rules/' "$TMP/repo/docs/adr/ADR-001-decision-records.md"
sed -i 's/^### ADR-001 — Decision records (Accepted)$/### ADR-001 — Decision record rules (Accepted)/' "$TMP/repo/docs/adr/DIGEST.md"
python3 "$TMP/repo/tools/fabric/adr.py" --root "$TMP/repo" index --write >/dev/null
git -C "$TMP/repo" add docs/adr/ADR-001-decision-records.md docs/adr/DIGEST.md
( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git commit -q -m "retitle, index left unstaged" >/dev/null 2>"$TMP/err" ); rc=$?
[[ $rc -eq 1 ]] && grep -q "index.json: stale" "$TMP/err" && pass "the staged tree is checked: an index left out of the commit is refused" || fail "a commit leaving the index behind was admitted (rc=$rc)" "$(cat "$TMP/err")"
git -C "$TMP/repo" add -A
( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git commit -q -m "retitle with its index" >/dev/null 2>"$TMP/err" ); rc=$?
[[ $rc -eq 0 ]] && pass "…and commits once the index is staged with it" || fail "the complete commit was refused" "$(cat "$TMP/err")"
sed -i 's|^\*\*Pillar:\*\* P2$|**Pillar:** P2\n**Evidence:** src/a.txt|' "$TMP/repo/docs/adr/ADR-001-decision-records.md"
[[ "$(try_commit docs/adr/DIGEST.md 'a record whose evidence lives elsewhere in the tree')" == 0 ]] && pass "Evidence anywhere in the staged tree resolves in the hook as in CI" || fail "the hook refused Evidence outside docs/adr" "$(cat "$TMP/err")"


echo "the one carve-out: a locale's translations, by the holder of the role named for the suffix"
SUFFIX="${LOGIN##*-}"; LOC="identities/roles/language-culture/locale/$SUFFIX"
bind language-culture; mkdir -p "$TMP/repo/$LOC" "$TMP/repo/identities/roles/language-culture/locale/zz"
[[ "$(try_commit "$LOC/team.md" 'ge team')" == 0 ]] && pass "language-culture bound on login *-$SUFFIX: locale/$SUFFIX/ commits" || fail "the holder's own locale refused" "$(cat "$TMP/err")"
git -C "$TMP/repo" log -1 --format=%B | grep -q '^Fabric-Role: language-culture$' && pass "…declaring its own role, not the coordinator's" || fail "trailer on a carve-out commit" "$(git -C "$TMP/repo" log -1 --format=%B)"
[[ "$(try_commit "identities/roles/language-culture/locale/zz/team.md" 'another locale')" == 1 ]] && grep -q "named for zz" "$TMP/err" && pass "another suffix's locale: refused, naming the suffix" || fail "another locale admitted" "$(cat "$TMP/err")"
mkdir -p "$TMP/repo/$LOC"; printf 'x\n' >> "$TMP/repo/$LOC/memory.md"; printf 'y\n' >> "$TMP/repo/src/a.txt"; git -C "$TMP/repo" add -A
( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git commit -qm 'locale plus code' 2>"$TMP/err" ); rc=$?; git -C "$TMP/repo" reset -q --hard
[[ $rc -eq 1 ]] && grep -q "agent-fabric itself" "$TMP/err" && pass "a locale file beside any other path: the whole-repository refusal" || fail "mixed commit admitted" "$(cat "$TMP/err")"
[[ "$(try_commit "identities/roles/language-culture/charter.md" 'the English charter')" == 1 ]] && pass "the role's English charter is not the locale: refused" || fail "charter admitted to the holder" "$(cat "$TMP/err")"
# The holder folds main into its branch: main moved elsewhere (a code file), the branch adds only its locale — allowed; a merge that also hand-edits a code file is refused.
git -C "$TMP/repo" checkout -q -b feat/ge; try_commit "$LOC/harness.md" 'ge harness' >/dev/null
git -C "$TMP/repo" checkout -q - ; bind fabric-coordinator; try_commit src/a.txt 'main moved' >/dev/null; MAIN_BRANCH="$(git -C "$TMP/repo" branch --show-current)"
git -C "$TMP/repo" checkout -q feat/ge; bind language-culture
( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git merge -q --no-ff --no-edit "$MAIN_BRANCH" 2>"$TMP/err" ); rc=$?
[[ $rc -eq 0 ]] && git -C "$TMP/repo" log -1 --format=%B | grep -q '^Fabric-Role: language-culture$' && pass "a merge of main into the holder's locale branch commits, declaring its role" || fail "the holder cannot fold main" "$(cat "$TMP/err")"
try_commit src/a.txt 'x' >/dev/null 2>&1; git -C "$TMP/repo" reset -q --hard; bind fabric-coordinator; git -C "$TMP/repo" checkout -q "$MAIN_BRANCH"; try_commit src/a.txt 'main moved again' >/dev/null; git -C "$TMP/repo" checkout -q feat/ge; bind language-culture
( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git merge -q --no-ff --no-commit "$MAIN_BRANCH" >/dev/null 2>&1; printf 'edited during the merge\n' >> src/a.txt; git add src/a.txt; AGENT_FABRIC_STATE_DIR="$TMP/state" git commit -qm 'merge plus a hand edit' 2>"$TMP/err" ); rc=$?
[[ $rc -eq 1 ]] && pass "a merge that also hand-edits outside the locale: refused" || fail "hand-edited merge admitted" "$(cat "$TMP/err")"
( cd "$TMP/repo" && git merge --abort 2>/dev/null; git reset -q --hard ); git -C "$TMP/repo" checkout -q "$MAIN_BRANCH"
bind backend-dev
[[ "$(try_commit "$LOC/memory.md" 'ge memory')" == 1 ]] && pass "another role on the same login: refused" || fail "wrong role admitted to a locale" "$(cat "$TMP/err")"
bind fabric-coordinator
[[ "$(try_commit "$LOC/memory.md" 'ge memory')" == 0 ]] && pass "the coordinator still commits anywhere, the locale included" || fail "coordinator refused in a locale" "$(cat "$TMP/err")"

echo "in agent-fabric itself an amend is a guarded change too"
bind backend-dev
( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git commit -q --amend --no-edit >/dev/null 2>"$TMP/err" ); rc=$?
[[ $rc == 1 ]] && pass "backend-dev bound: an amend in the fabric is refused" || fail "amend admitted under backend-dev" "$(cat "$TMP/err")"
bind fabric-coordinator
( cd "$TMP/repo" && git commit -q --amend -m 'rewritten' >/dev/null 2>"$TMP/err" ); rc=$?   # message without a trailer
( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git commit -q --amend --no-edit >/dev/null 2>"$TMP/err" ); rc=$?
[[ $rc == 0 ]] && pass "fabric-coordinator bound: the amend commits" || fail "amend refused" "$(cat "$TMP/err")"
git -C "$TMP/repo" log -1 --format=%B | grep -q '^Fabric-Role: fabric-coordinator$' && pass "…and the amend carries the trailer (git am + amend is the handover route)" || fail "no trailer on an amend" "$(git -C "$TMP/repo" log -1 --format=%B)"

echo "a merge that only folds main's .agent-fabric/ changes is no change of its own"
# main gets a drain (coordinator); a backend-dev branch then folds main.
bind fabric-coordinator; new_repo
git -C "$TMP/repo" checkout -q -b feature; printf 'feature\n' >> "$TMP/repo/src/a.txt"; git -C "$TMP/repo" add -A
( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git commit -qm feature )
git -C "$TMP/repo" checkout -q master 2>/dev/null || git -C "$TMP/repo" checkout -q main
[[ "$(try_commit .agent-fabric/memory/backend-dev/workflow.md 'drain on main')" == 0 ]] || fail "setup: drain on main" "$(cat "$TMP/err")"
git -C "$TMP/repo" checkout -q feature; bind backend-dev
( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git merge -q --no-ff --no-edit "$(git rev-parse --abbrev-ref @{-1})" >/dev/null 2>"$TMP/err" ); rc=$?
[[ $rc == 0 ]] && pass "backend-dev bound: the fold commits" || fail "the fold was refused" "$(cat "$TMP/err")"
git -C "$TMP/repo" log -1 --format=%B | grep -q '^Fabric-Role: backend-dev$' && pass "…and declares the role that folded it, as every commit does" || fail "no trailer on the fold" "$(git -C "$TMP/repo" log -1 --format=%B)"
[[ -z "$(git -C "$TMP/repo" diff HEAD^2 HEAD -- .agent-fabric/)" ]] && pass "…and .agent-fabric/ equals main's" || fail "fold altered .agent-fabric/"

echo "a merge that also hand-edits a slice is refused"
git -C "$TMP/repo" reset -q --hard HEAD^ ; bind backend-dev
( cd "$TMP/repo" && AGENT_FABRIC_STATE_DIR="$TMP/state" git merge -q --no-ff --no-commit "$(git rev-parse --abbrev-ref @{-1})" >/dev/null 2>&1; printf 'by hand\n' >> .agent-fabric/memory/backend-dev/workflow.md; git add -A; AGENT_FABRIC_STATE_DIR="$TMP/state" git commit -qm 'fold plus edit' >/dev/null 2>"$TMP/err" ); rc=$?
[[ $rc == 1 ]] && pass "backend-dev bound: refused" || fail "a merge carrying a hand edit was admitted"
grep -q "this agent's binding holds: backend-dev" "$TMP/err" && pass "…by the fence" || fail "wording" "$(cat "$TMP/err")"
( cd "$TMP/repo" && git merge --abort 2>/dev/null; git reset -q --hard )

echo "the attribution ban still holds on the same hook"
bind fabric-coordinator; new_repo
[[ "$(try_commit src/a.txt $'x\n\nCo-authored-by: Someone <s@e>')" == 1 ]] && pass "Co-authored-by is still refused" || fail "ban lost"

echo
echo "in a managed project, its own docs/adr/ is its own"
bind fabric-coordinator; new_repo
mkdir -p "$TMP/repo/docs/adr"; printf 'not ours\n' > "$TMP/repo/docs/adr/index.json"
[[ "$(try_commit docs/adr/index.json 'a project record')" == 0 ]] && pass "a managed project's docs/adr/ is not checked by the fabric's hook" || fail "the fabric's hook judged a project's records" "$(cat "$TMP/err")"

if (( failures )); then echo "test_hooks: $failures assertion(s) FAILED"; exit 1; fi
echo "all assertions passed"
