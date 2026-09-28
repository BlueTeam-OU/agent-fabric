#!/usr/bin/env bash
# tests/test_fabric-branches.sh — bin/fabric-branches: the report deletes
# nothing; the sweep deletes exactly what is wholly on origin/main, keeps
# the rest, and never touches a remote branch.
set -uo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CMD="$ROOT/bin/fabric-branches"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fails=0
ok() { echo "  ✓ $1"; }
bad() { echo "  ✗ $1" >&2; [[ -n "${2:-}" ]] && printf '      %s\n' "$2" >&2; fails=$((fails + 1)); }

# No network: a gh that answers "no pull request" for every branch.
mkdir -p "$T/bin"; printf '#!/bin/sh\nexit 0\n' > "$T/bin/gh"; chmod +x "$T/bin/gh"
export PATH="$T/bin:$PATH" AGENT_FABRIC_STATE_DIR="$T/state"
g() { git -C "$1" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "${@:2}"; }
me="$(hostname -s)/$(id -un)"

git init -q --bare -b main "$T/origin.git"
git clone -q "$T/origin.git" "$T/wc" 2>/dev/null
g "$T/wc" commit -q --allow-empty -m base; g "$T/wc" push -q origin HEAD:main
# merged: its commit is on main. owed: one commit that is not. theirs: a
# local copy of another agent's branch, merged.
g "$T/wc" checkout -q -b "$me/merged"; g "$T/wc" commit -q --allow-empty -m merged
g "$T/wc" push -q origin "$me/merged" "$me/merged:main" 2>/dev/null; g "$T/wc" branch -q -u "origin/$me/merged"
g "$T/wc" checkout -q -b "$me/owed"; g "$T/wc" commit -q --allow-empty -m owed
g "$T/wc" push -q -u origin "$me/owed" 2>/dev/null
g "$T/wc" checkout -q main; g "$T/wc" pull -q --ff-only origin main
g "$T/wc" push -q origin "main:other-host/other-login/fix" 2>/dev/null
g "$T/wc" fetch -q origin; g "$T/wc" branch -q theirs "origin/other-host/other-login/fix"
g "$T/wc" worktree add -q "$T/wt-clean" -b wt-clean main 2>/dev/null
g "$T/wc" worktree add -q "$T/wt-dirty" -b wt-dirty main 2>/dev/null; echo x > "$T/wt-dirty/new"

echo "fabric-branches: the report"
out="$(cd "$T/wc" && "$CMD" 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && ok "exit 0" || bad "report (rc=$rc)" "$out"
grep -qE "^  0 +$me/merged " <<<"$out" && grep -qE "^  1 +$me/owed " <<<"$out" && ok "…counts each branch against origin/main" || bad "counts" "$out"
grep -q "theirs  upstream=origin/other-host/other-login/fix  (tracks another agent's branch" <<<"$out" && ok "…names a copy of another agent's branch" || bad "other agent" "$out"
grep -q "      [0-9a-f]* owed" <<<"$out" && ok "…lists the commits off main" || bad "commits" "$out"
grep -q "wt-dirty  1 uncommitted change(s)" <<<"$out" && ok "…and a worktree's changes" || bad "worktree status" "$out"
[[ -n "$(g "$T/wc" branch --list "$me/merged")" && -d "$T/wt-clean" ]] && ok "…and deletes nothing" || bad "report deleted something"

echo "fabric-branches: refusals"
echo dirt > "$T/wc/dirt"
out="$(cd "$T/wc" && "$CMD" --sweep 2>&1)"; rc=$?
[[ $rc -eq 2 && -n "$(g "$T/wc" branch --list "$me/merged")" ]] && grep -q "uncommitted changes" <<<"$out" && ok "a dirty tree: exit 2, nothing deleted" || bad "dirty (rc=$rc)" "$out"
rm "$T/wc/dirt"
g "$T/wc" remote set-url origin "$T/nowhere.git"
out="$(cd "$T/wc" && "$CMD" --sweep 2>&1)"; rc=$?
[[ $rc -eq 2 && -n "$(g "$T/wc" branch --list "$me/merged")" ]] && grep -q "fetch origin failed" <<<"$out" && ok "a failed fetch: exit 2, nothing deleted" || bad "fetch (rc=$rc)" "$out"
g "$T/wc" remote set-url origin "$T/origin.git"
out="$(cd "$T" && "$CMD" 2>&1)"; rc=$?
[[ $rc -eq 2 ]] && ok "outside a working copy: exit 2" || bad "no repo (rc=$rc)" "$out"

echo "fabric-branches: the sweep"
out="$(cd "$T/wc" && "$CMD" --sweep 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && ok "exit 0" || bad "sweep (rc=$rc)" "$out"
[[ -z "$(g "$T/wc" branch --list "$me/merged")" && -z "$(g "$T/wc" branch --list theirs)" ]] \
    && grep -qE "deleted $me/merged \([0-9a-f]+\)" <<<"$out" && ok "…deletes what shows 0, with its SHA" || bad "zeros" "$out"
[[ -n "$(g "$T/wc" branch --list "$me/owed")" && -n "$(g "$T/wc" branch --list main)" ]] && ok "…keeps a branch with commits off main, and main" || bad "kept" "$out"
[[ ! -d "$T/wt-clean" && -d "$T/wt-dirty" && -n "$(g "$T/wc" branch --list wt-dirty)" ]] && ok "…removes a clean worktree at 0, keeps one with changes" || bad "worktrees" "$out"
[[ -n "$(git -C "$T/origin.git" branch --list "$me/merged")" && -n "$(git -C "$T/origin.git" branch --list other-host/other-login/fix)" ]] && ok "…and no remote branch is touched" || bad "remote touched"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert sys.argv[2] in d, d' "$T/state/agents/$(id -un)/branch-sweep.json" "$(cd "$T/wc" && git rev-parse --show-toplevel)" \
    && ok "…and the sweep is recorded for the working copy" || bad "no record"

if (( fails )); then echo "test_fabric-branches: $fails FAILED"; exit 1; fi
echo "test_fabric-branches: all assertions passed"
