#!/usr/bin/env bash
# runtime/claude-code/hooks/test_statusline.sh — the status line's branch
# segment: a branch name inside a repository, the short SHA on a detached
# HEAD (a link icon, not the branch one), and NO segment outside a repository (the parent projects/
# workspace), which used to read "detached" and sent the owner looking for
# a branch nobody had made (2026-09-15); and the leading bracket — Claude
# Code's version, the model and the live effort level (owner, 2026-09-24),
# each dropped when the session JSON does not carry it. Each case runs the
# real script against a throwaway git repo.
set -uo pipefail
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/statusline.sh"
failures=0
SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT
pass() { echo "  ok   $1"; }
fail() { echo "  FAIL $1: $2" >&2; failures=$((failures + 1)); }
# gh is mocked on PATH: MOCK_PR holds "<STATE> <number>" lines or nothing,
# MOCK_GH_FAIL makes it exit 1; the cache lives under the sandbox so no
# real cache is read or written, and a TTL of 0 means every call asks.
# A GH_REPO in the caller's environment would name the repository for
# every case and hide the origin reading the fork case tests.
unset GH_REPO
mkdir -p "$SANDBOX/bin"
cat > "$SANDBOX/bin/gh" <<'GH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$MOCK_GH_CALLS"
[ -f "$MOCK_GH_FAIL" ] && exit 1
if [ -s "$MOCK_PR" ]; then
  awk '{printf "%s{\"state\":\"%s\",\"number\":%s}", (NR>1?",":"["), $1, $2} END{print (NR?"]":"[]")}' "$MOCK_PR"
else echo "[]"; fi
GH
chmod +x "$SANDBOX/bin/gh"
export MOCK_PR="$SANDBOX/pr" MOCK_GH_FAIL="$SANDBOX/ghfail" MOCK_GH_CALLS="$SANDBOX/ghcalls" XDG_CACHE_HOME="$SANDBOX/cache" AGENT_FABRIC_STATUSLINE_PR_TTL=0
line_of() { printf '{"workspace":{"current_dir":"%s"},"model":{"display_name":"M"}}' "$1" | PATH="$SANDBOX/bin:$PATH" bash "$UNDER_TEST" 2>/dev/null; }
# The same, with what a current harness sends beside the model: its version
# and the effort block (optional in the JSON — only a model that takes a level has one).
line_full() { printf '{"workspace":{"current_dir":"%s"},"model":{"display_name":"M"},"version":"1.2.3","effort":{"level":"high"}}' "$1" | PATH="$SANDBOX/bin:$PATH" bash "$UNDER_TEST" 2>/dev/null; }
line_versioned() { printf '{"workspace":{"current_dir":"%s"},"model":{"display_name":"M"},"version":"1.2.3"}' "$1" | PATH="$SANDBOX/bin:$PATH" bash "$UNDER_TEST" 2>/dev/null; }
g() { git -C "$repo" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@" >/dev/null 2>&1; }

repo="$SANDBOX/clone"; mkdir -p "$repo"; g init -q; g commit -q --allow-empty -m one; g branch -M main
# A fork clone: origin is the fork, an upstream remote the project it came
# from, which gh's default would pick (agent-fabric #109).
g remote add origin git@github.com:fork-org/proj.git; g remote add upstream https://github.com/up-org/proj.git
out="$(line_of "$repo")"
[[ "$out" == *"🔀 N/A 📁 clone 🌿 main" ]] && pass "inside a repository, no pull request: 🔀 N/A before the folder, then the branch" || fail "branch / no PR" "$out"
grep -q -- "--repo fork-org/proj" "$MOCK_GH_CALLS" && ! grep -q "up-org" "$MOCK_GH_CALLS" \
  && pass "a fork clone asks about origin's repository, never upstream's" || fail "fork repo" "$(cat "$MOCK_GH_CALLS")"
printf 'OPEN 386\n' > "$MOCK_PR"
out="$(line_of "$repo")"
[[ "$out" == *"🔀 #386 📁 clone 🌿 main" ]] && pass "an open pull request: 🔀 #386 before the folder" || fail "open PR" "$out"
printf 'MERGED 386\n' > "$MOCK_PR"
out="$(line_of "$repo")"
[[ "$out" == *"✅ #386 📁 clone 🌿 main" ]] && pass "a merged pull request: ✅ #386 (the branch is done)" || fail "merged PR" "$out"
printf 'MERGED 380\nOPEN 386\n' > "$MOCK_PR"
out="$(line_of "$repo")"
[[ "$out" == *"🔀 #386 📁"* ]] && pass "an open PR wins over an older merged one on the same branch" || fail "open over merged" "$out"
: > "$MOCK_PR"; : > "$MOCK_GH_FAIL"
out="$(line_of "$repo")"
[[ "$out" == *"🔀 #? 📁 clone"* ]] && pass "gh failing: #? (unknown), never N/A" || fail "gh fail" "$out"
rm -f "$MOCK_GH_FAIL"
# The cache: with a TTL the second draw does not ask gh at all (an
# unknown from the failing gh above was NOT cached, so the first draw asks).
printf 'OPEN 386\n' > "$MOCK_PR"; AGENT_FABRIC_STATUSLINE_PR_TTL=300 line_of "$repo" >/dev/null
: > "$MOCK_GH_FAIL"
out="$(AGENT_FABRIC_STATUSLINE_PR_TTL=300 line_of "$repo")"
[[ "$out" == *"🔀 #386 📁"* ]] && pass "within the TTL the cached answer is drawn and gh is not asked" || fail "cache" "$out"
rm -f "$MOCK_GH_FAIL"; : > "$MOCK_PR"; rm -rf "$SANDBOX/cache"
# Nothing names the repository (origin off github.com, no GH_REPO): the
# pull request is unknown, and gh is never asked to guess one.
g remote set-url origin https://example.com/fork-org/proj.git; : > "$MOCK_GH_CALLS"
out="$(GH_REPO= line_of "$repo")"
[[ "$out" == *"🔀 #? 📁 clone"* && ! -s "$MOCK_GH_CALLS" ]] && pass "no repository named: #?, and gh is not asked" || fail "no repo" "$out / $(cat "$MOCK_GH_CALLS")"
g remote set-url origin git@github.com:fork-org/proj.git; rm -rf "$SANDBOX/cache"
git -C "$repo" checkout -q --detach main
sha="$(git -C "$repo" rev-parse --short HEAD)"
out="$(line_of "$repo")"
[[ "$out" == *"📁 clone 🔗 $sha" && "$out" != *"🔀"* && "$out" != *"N/A"* ]] && pass "a detached HEAD: a link and its short SHA, no branch icon and no pull-request segment" || fail "detached" "$out"
[[ "$out" != *"🌿"* ]] && pass "…and no branch icon on a detached HEAD" || fail "branch icon on detached" "$out"
plain="$SANDBOX/projects"; mkdir -p "$plain"
out="$(line_of "$plain")"
[[ "$out" == *"📁 projects" && "$out" != *"🌿"* && "$out" != *"🔗"* && "$out" != *"🔀"* ]] && pass "outside a repository: no ref segment and no pull-request segment" || fail "no repo" "$out"
unborn="$SANDBOX/fresh"; mkdir -p "$unborn"; git -C "$unborn" init -q -b main
git -C "$unborn" remote add origin https://github.com/fork-org/fresh.git
out="$(line_of "$unborn")"
[[ "$out" == *"🔀 N/A 📁 fresh 🌿 main" ]] && pass "a repository with no commit yet: still its branch name, and N/A for the pull request" || fail "unborn" "$out"
[[ "$out" != *detached* ]] && pass "…and the word 'detached' appears nowhere" || fail "detached word" "$out"

# The leading bracket: version · model · effort, each present only when the
# session JSON carries it — no invented level for a model that takes none.
out="$(line_full "$repo")"
[[ "$out" == "[1.2.3 · M · high] 👤 "* ]] && pass "the bracket reads the bare version · model · effort, in that order" || fail "bracket full" "$out"
out="$(line_versioned "$repo")"
[[ "$out" == "[1.2.3 · M] 👤 "* ]] && pass "no effort block in the JSON: version · model, and no level is invented" || fail "bracket no effort" "$out"
out="$(line_of "$repo")"
[[ "$out" == "[M] 👤 "* ]] && pass "neither version nor effort sent: the model alone, as before" || fail "bracket model only" "$out"

if (( failures )); then echo "test_statusline: FAILED — $failures"; exit 1; fi
echo "test_statusline: OK — all assertions passed."
