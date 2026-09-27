#!/usr/bin/env bash
# runtime/github/test_trial-merge.sh
#
# Tests for trial-merge.sh against a throwaway origin and clone: branches
# that combine and branches that conflict, the project's check passing,
# failing and timing out, a run killed mid-check, two runs at once, a ref
# that is not on origin, a failed fetch — and after every one of them the
# caller's clone exactly as it was and no worktree left behind.
#
# Exit codes:
#   0  all assertions passed
#   1  one or more assertions failed

set -u

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/trial-merge.sh"
command -v jq >/dev/null 2>&1 || { echo "test: jq is required" >&2; exit 1; }

failures=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1" >&2; printf '%s\n' "${2:-}" | sed 's/^/      /' >&2; failures=$((failures + 1)); }

SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT
SCRATCH="$SANDBOX/scratch"; mkdir -p "$SCRATCH"

git init -q --bare -b main "$SANDBOX/origin.git"
git init -q -b main "$SANDBOX/repo"; cd "$SANDBOX/repo" || exit 1
git config user.email t@example.invalid; git config user.name t; git config commit.gpgsign false
git remote add origin "$SANDBOX/origin.git"
printf 'one\ntwo\nthree\n' > f.txt; git add -A; git commit -q -m base; git push -q origin main
br() { git checkout -q -b "$1" main; eval "$2"; git add -A; git commit -q -m "$1"; git push -q origin "$1"; git checkout -q main; }
br h/a/one   "sed -i 's/^one$/ONE/' f.txt"
br h/b/two   "printf 'new\n' > g.txt"
br h/c/clash "sed -i 's/^one$/uno/' f.txt"
git remote set-head origin main >/dev/null 2>&1 || git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
git checkout -q -b local-work main; printf 'dirty\n' >> f.txt   # the caller's own state, uncommitted

snap() { git -C "$SANDBOX/repo" rev-parse HEAD; git -C "$SANDBOX/repo" status --porcelain; git -C "$SANDBOX/repo" for-each-ref --format='%(refname) %(objectname)' refs/heads; git -C "$SANDBOX/repo" diff; }
before="$(snap)"
origin_refs() { git --git-dir="$SANDBOX/origin.git" for-each-ref --format='%(refname) %(objectname)'; }
origin_before="$(origin_refs)"
clean() { [[ "$before" == "$(snap)" ]] && [[ -z "$(ls -A "$SCRATCH")" ]] && [[ "$(git -C "$SANDBOX/repo" worktree list | wc -l)" -eq 1 ]]; }
run() { (cd "$SANDBOX/repo" && TMPDIR="$SCRATCH" AGENT_FABRIC_TRIAL_MIN_FREE_KB=0 bash "$UNDER_TEST" "$@" 2>&1); }
cfg() { printf '%s' "$1" > "$SANDBOX/trial.json"; }

echo "trial-merge: combine, conflict, the project's check, and nothing left behind"
out="$(run h/a/one h/b/two --json)"; rc=$?
[[ $rc -eq 0 && "$(jq -r .result <<<"$out")" == combines && "$(jq -r '.tree | length' <<<"$out")" == 40 && "$(jq -r '.refs | map(.branch) | join(",")' <<<"$out")" == "h/a/one,h/b/two" ]] \
  && pass "two independent branches combine: exit 0, a tree hash, the shas tried" || fail "combine wrong (rc=$rc)" "$out"
clean && pass "…the caller's HEAD, index, working tree and branches untouched; no worktree left" || fail "the clone changed or a worktree was left" "$(git worktree list; ls -A "$SCRATCH")"
manual="$(cd "$SANDBOX" && rm -rf m && git clone -q "$SANDBOX/origin.git" m && cd m && git -c user.name=t -c user.email=t@t merge -q --no-ff --no-edit origin/h/a/one && git -c user.name=t -c user.email=t@t merge -q --no-ff --no-edit origin/h/b/two && git rev-parse 'HEAD^{tree}')"; rm -rf "$SANDBOX/m"
[[ "$(jq -r .tree <<<"$out")" == "$manual" ]] && pass "…the reported tree is the tree of the same merges made by hand, in the order given" || fail "tree differs from a manual merge" "$manual vs $(jq -r .tree <<<"$out")"
[[ "$origin_before" == "$(origin_refs)" ]] && pass "…and the remote's refs are unchanged: nothing pushed" || fail "the remote changed"

out="$(run h/a/one h/c/clash)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'conflicts — h/c/clash did not merge' <<<"$out" && grep -q '    f.txt' <<<"$out" \
  && pass "the same line changed twice: conflicts, naming the second ref and the path; exit 1" || fail "conflict wrong (rc=$rc)" "$out"
clean && pass "…and nothing left behind" || fail "leftovers after a conflict"

cfg '{"check": ["sh", "-c", "test -f g.txt && grep -q ONE f.txt"]}'
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one h/b/two --check)"; rc=$?
[[ $rc -eq 0 ]] && grep -q 'check passed (exit 0)' <<<"$out" && pass "--check runs the project's check on the combined tree: passed" || fail "check pass wrong (rc=$rc)" "$out"
cfg '{"check": ["sh", "-c", "echo building; echo the suite failed >&2; exit 3"]}'
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one --check)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'check failed (exit 3)' <<<"$out" && grep -q 'the suite failed' <<<"$out" \
  && pass "…failed: exit 1 with its last lines" || fail "check failure wrong (rc=$rc)" "$out"
clean && pass "…and nothing left behind" || fail "leftovers after a failed check"
cfg '{"check": ["sleep", "30"], "timeout_s": 1}'
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one --check)"; rc=$?
[[ $rc -eq 2 ]] && grep -q 'check unavailable' <<<"$out" && pass "…timed out: unavailable, exit 2 — never a pass" || fail "timeout wrong (rc=$rc)" "$out"
cfg '{"check": ["no-such-check-command"]}'
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one --check)"; rc=$?
[[ $rc -eq 2 ]] && grep -q 'check unavailable' <<<"$out" && pass "…a check command that is not there: unavailable" || fail "missing command wrong (rc=$rc)" "$out"
V='"verdict": "^trial-check: (PASS|FAIL|UNAVAILABLE)"'
cfg "{\"check\": [\"sh\", \"-c\", \"echo 'trial-check: PASS on x'; exit 2\"], $V}"
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one --check)"; rc=$?
[[ $rc -eq 0 ]] && grep -q 'check passed' <<<"$out" && pass "a declared verdict line wins over the exit code: PASS with exit 2 is a pass" || fail "verdict PASS wrong (rc=$rc)" "$out"
cfg "{\"check\": [\"sh\", \"-c\", \"echo 'trial-check: FAIL on x'; exit 0\"], $V}"
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one --check)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'check failed' <<<"$out" && pass "…FAIL with exit 0 is a failure" || fail "verdict FAIL wrong (rc=$rc)" "$out"
cfg "{\"check\": [\"sh\", \"-c\", \"echo 'trial-check: UNAVAILABLE on x'; exit 2\"], $V}"
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one --check)"; rc=$?
[[ $rc -eq 2 ]] && grep -q 'check unavailable' <<<"$out" && pass "…UNAVAILABLE is unavailable" || fail "verdict UNAVAILABLE wrong (rc=$rc)" "$out"
cfg "{\"check\": [\"sh\", \"-c\", \"echo make: no rule to make target; exit 0\"], $V}"
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one --check)"; rc=$?
[[ $rc -eq 2 ]] && grep -q 'check unavailable' <<<"$out" && pass "…a declared verdict that never appears is unavailable, even on exit 0" || fail "missing verdict read as a pass (rc=$rc)" "$out"
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one h/c/clash --check)"; rc=$?
[[ $rc -eq 1 ]] && grep -q 'check: not run — the refs did not combine' <<<"$out" && pass "…not run on refs that conflict, and said" || fail "check on a conflict wrong (rc=$rc)" "$out"
cfg '{}'
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one --check)"; rc=$?
[[ $rc -eq 0 ]] && grep -q 'none declared' <<<"$out" && pass "…a project that declares none: merge only, and said" || fail "no-check wrong (rc=$rc)" "$out"

cfg '{"check": ["sleep", "37.25"]}'   # a sentinel no other process runs
# The script's own process is the one signalled (a subshell around it
# would take the signal and leave the script running to its end).
cd "$SANDBOX/repo" || exit 1
TMPDIR="$SCRATCH" AGENT_FABRIC_TRIAL_MIN_FREE_KB=0 AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" bash "$UNDER_TEST" h/a/one --check >/dev/null 2>&1 &
victim=$!
for _ in $(seq 1 50); do [[ -n "$(ls -A "$SCRATCH" 2>/dev/null)" ]] && break; sleep 0.1; done
for _ in $(seq 1 50); do pgrep -u "$(id -u)" -fx "sleep 37.25" >/dev/null && break; sleep 0.1; done
kill -TERM "$victim" 2>/dev/null; wait "$victim" 2>/dev/null
sleep 0.5
clean && pass "a run killed (TERM) during the check leaves no worktree and no file" || fail "leftovers after a kill" "$(git worktree list; ls -A "$SCRATCH")"
! pgrep -u "$(id -u)" -fx "sleep 37.25" >/dev/null && pass "…and no check process: the check's whole group went with it" || { fail "the check outlived the killed run" "$(pgrep -a -u "$(id -u)" -fx 'sleep 37.25')"; pkill -u "$(id -u)" -fx "sleep 37.25"; }

TMPDIR="$SCRATCH" AGENT_FABRIC_TRIAL_MIN_FREE_KB=0 AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" bash "$UNDER_TEST" h/a/one --check >/dev/null 2>&1 &
victim=$!
for _ in $(seq 1 50); do pgrep -u "$(id -u)" -fx "sleep 37.25" >/dev/null && break; sleep 0.1; done
kill -INT "$victim" 2>/dev/null; wait "$victim" 2>/dev/null; sleep 0.5
clean && ! pgrep -u "$(id -u)" -fx "sleep 37.25" >/dev/null && pass "…and interrupted (INT): the same — the caller's uncommitted edit and worktree list as they were" \
  || { fail "leftovers after INT" "$(git worktree list; ls -A "$SCRATCH")"; pkill -u "$(id -u)" -fx "sleep 37.25"; }

# A worktree add that loses a race once (another run's prune, a config
# lock) is retried, not reported as a failed trial: a git that fails the
# first add and then behaves (CI, #52, "concurrent runs disagreed").
mkdir -p "$SANDBOX/flakybin"; rm -f "$SANDBOX/flaky.count"
real_git="$(command -v git)"
cat > "$SANDBOX/flakybin/git" <<SHIM
#!/usr/bin/env bash
if [[ "\$*" == *"worktree add"* && ! -f "$SANDBOX/flaky.count" ]]; then
    : > "$SANDBOX/flaky.count"; echo "fatal: could not lock config file .git/config: File exists" >&2; exit 128
fi
exec "$real_git" "\$@"
SHIM
chmod +x "$SANDBOX/flakybin/git"
out="$(cd "$SANDBOX/repo" && PATH="$SANDBOX/flakybin:$PATH" TMPDIR="$SCRATCH" AGENT_FABRIC_TRIAL_MIN_FREE_KB=0 bash "$UNDER_TEST" h/a/one h/b/two --json 2>&1)"; rc=$?
[[ $rc -eq 0 && -f "$SANDBOX/flaky.count" ]] && [[ "$(jq -r .result <<<"$out" 2>/dev/null)" == combines ]] \
  && pass "a worktree add that fails once is retried, and the trial runs" || fail "a transient worktree add failure ended the trial" "$out"
clean && pass "…and the retry left nothing" || fail "leftovers after a retried add" "$(git worktree list; ls -A "$SCRATCH")"

( run h/a/one h/b/two --json > "$SANDBOX/r1" ) & ( run h/a/one h/b/two --json > "$SANDBOX/r2" ) & wait
[[ "$(jq -r .tree "$SANDBOX/r1")" == "$(jq -r .tree "$SANDBOX/r2")" && "$(jq -r .result "$SANDBOX/r1")" == combines ]] \
  && pass "two runs at once on the same refs: each its own worktree, the same result" || fail "concurrent runs disagreed" "$(cat "$SANDBOX/r1" "$SANDBOX/r2")"
clean && pass "…and neither left anything" || fail "leftovers after concurrent runs"

out="$(run h/a/one h/zz/nowhere)"; rc=$?
[[ $rc -eq 2 ]] && grep -q 'h/zz/nowhere is not a branch on origin; nothing tried' <<<"$out" && clean \
  && pass "a ref not on origin: exit 2, nothing tried, nothing left" || fail "unknown ref wrong (rc=$rc)" "$out"
git -C "$SANDBOX/repo" remote set-url origin "$SANDBOX/nowhere.git"
out="$(run h/a/one)"; rc=$?
git -C "$SANDBOX/repo" remote set-url origin "$SANDBOX/origin.git"
[[ $rc -eq 2 ]] && grep -q 'git fetch origin failed; nothing tried' <<<"$out" && pass "a failed fetch: exit 2, nothing tried" || fail "failed fetch not said (rc=$rc)" "$out"
out="$(cd "$SANDBOX/repo" && TMPDIR="$SCRATCH" AGENT_FABRIC_TRIAL_MIN_FREE_KB=999999999999 bash "$UNDER_TEST" h/a/one 2>&1)"; rc=$?
[[ $rc -eq 2 ]] && grep -q 'nothing tried' <<<"$out" && grep -q 'KB free' <<<"$out" && pass "too little free space: refused before starting" || fail "space check wrong (rc=$rc)" "$out"
out="$(run)"; rc=$?
[[ $rc -eq 2 ]] && pass "no ref named: a usage error" || fail "no refs accepted (rc=$rc)" "$out"

echo "trial-merge: the review of #47's cases"
# A clone whose hooks refuse every commit (every managed clone runs hooks):
# the trial merge is never committed anywhere, so the hooks are not run.
mkdir -p "$SANDBOX/hooks"; printf '#!/bin/sh\necho "hook: refused" >&2\nexit 1\n' > "$SANDBOX/hooks/commit-msg"; cp "$SANDBOX/hooks/commit-msg" "$SANDBOX/hooks/pre-merge-commit"; chmod +x "$SANDBOX/hooks/"*
git -C "$SANDBOX/repo" config core.hooksPath "$SANDBOX/hooks"
out="$(run h/a/one h/b/two)"; rc=$?
git -C "$SANDBOX/repo" config --unset core.hooksPath
[[ $rc -eq 0 ]] && grep -q '^combines' <<<"$out" && pass "a clone whose hooks refuse commits: the refs still combine — no hook runs on a trial merge" || fail "a hook turned a clean merge into a failure (rc=$rc)" "$out"
before="$(snap)"   # the hooksPath round trip is config, not the clone's state under test
# A branch with no history in common: not a conflict, and never said to be one.
( cd "$SANDBOX/repo" && git checkout -q --orphan h/d/alien && git rm -rfq . && printf 'x\n' > alien.txt && git add -A && git commit -q -m alien && git push -q origin h/d/alien && git checkout -q local-work 2>/dev/null || git checkout -q -f local-work )
printf 'dirty\n' >> "$SANDBOX/repo/f.txt" 2>/dev/null; git -C "$SANDBOX/repo" checkout -q local-work 2>/dev/null
before="$(snap)"
out="$(run h/a/one h/d/alien --json)"; rc=$?
[[ $rc -eq 2 && "$(jq -r .result <<<"$out")" == "could not merge" && "$(jq -r '.conflicted | length' <<<"$out")" == 0 ]] && grep -q 'unrelated histories' <<<"$(jq -r .git <<<"$out")" \
  && pass "unrelated histories: 'could not merge' with git's line, exit 2 — never 'conflicts'" || fail "a non-conflict failure read as a conflict (rc=$rc)" "$out"
clean && pass "…and nothing left behind" || fail "leftovers after a failed merge"
# A check that starts something in the background and exits 0.
cfg '{"check": ["sh", "-c", "sleep 41.75 & exit 0"]}'
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one --check)"; rc=$?; sleep 0.3
! pgrep -u "$(id -u)" -fx "sleep 41.75" >/dev/null && pass "a check that left a process behind and exited: its whole group is gone too" \
  || { fail "a background process of the check outlived the run" "$(pgrep -a -u "$(id -u)" -fx 'sleep 41.75')"; pkill -u "$(id -u)" -fx "sleep 41.75"; }
# A held lease (fabric-lease's exit 75) is unavailable, never a failure.
cfg '{"check": ["sh", "-c", "exit 75"]}'
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one --check)"; rc=$?
[[ $rc -eq 2 ]] && grep -q 'check unavailable' <<<"$out" && pass "a lease still held (75): unavailable" || fail "a held lease read otherwise (rc=$rc)" "$out"
# A dead run's leftovers — its worktree, pid and output files — are swept by the next run.
mkdir -p "$SCRATCH/trial-merge.DEAD01"; echo 999999 > "$SCRATCH/trial-merge.DEAD01.pid"; echo old > "$SCRATCH/trial-merge.DEAD01.out"
run h/a/one >/dev/null
[[ -z "$(ls -A "$SCRATCH")" ]] && pass "a dead run's worktree, pid and output file are swept by the next run" || fail "a dead run's files survived" "$(ls -A "$SCRATCH")"

echo "trial-merge: the re-review of #47's cases"
# A declared lease runs the check in a group of its own, as fabric-lease
# does (set -m around the child): the check's leftovers are ended anyway.
mkdir -p "$SANDBOX/leasebin"
cat > "$SANDBOX/leasebin/fabric-lease" <<'LEASE'
#!/usr/bin/env bash
shift; [[ "$1" == "--" ]] && shift
set -m; "$@" & child=$!; set +m
wait "$child"
LEASE
chmod +x "$SANDBOX/leasebin/fabric-lease"
cfg '{"check": ["sh", "-c", "cd / && sleep 43.5 & exit 0"], "lease": "trial"}'   # it leaves the worktree, too
out="$(cd "$SANDBOX/repo" && PATH="$SANDBOX/leasebin:$PATH" TMPDIR="$SCRATCH" AGENT_FABRIC_TRIAL_MIN_FREE_KB=0 AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" bash "$UNDER_TEST" h/a/one --check 2>&1)"; rc=$?; sleep 0.3
[[ $rc -eq 0 ]] && grep -q 'check passed' <<<"$out" && pass "…a check under a declared lease runs and passes" || fail "the leased check did not run (rc=$rc)" "$out"
! pgrep -u "$(id -u)" -fx "sleep 43.5" >/dev/null && pass "…and what it left running in its own group under the lease is ended too" \
  || { fail "a leased check's leftover outlived the run" "$(pgrep -a -u "$(id -u)" -fx 'sleep 43.5')"; pkill -u "$(id -u)" -fx "sleep 43.5"; }
clean && pass "…nothing left behind" || fail "leftovers after a leased check"
# The check on refs that did not merge says so, whatever the reason.
cfg '{"check": ["true"]}'
out="$(AGENT_FABRIC_TRIAL_CONFIG="$SANDBOX/trial.json" run h/a/one h/d/alien --check --json)"; rc=$?
[[ $rc -eq 2 && "$(jq -r .check <<<"$out")" == "not run: did not combine" ]] && pass "a merge that failed without a conflict: its check reads 'not run: did not combine'" || fail "wrong check state on a failed merge (rc=$rc)" "$out"
# A worktree left without a pid by a run killed before writing it: swept once an hour old.
mkdir -p "$SCRATCH/trial-merge.NOPID1"; touch -d '2 hours ago' "$SCRATCH/trial-merge.NOPID1"
mkdir -p "$SCRATCH/trial-merge.NOPID2"
run h/a/one >/dev/null
[[ ! -e "$SCRATCH/trial-merge.NOPID1" && -d "$SCRATCH/trial-merge.NOPID2" ]] && pass "a pid-less worktree an hour old is swept; a fresh one (a run just starting) is left" || fail "the pid-less sweep is wrong" "$(ls -A "$SCRATCH")"
rm -rf "$SCRATCH/trial-merge.NOPID2"

echo
if [[ $failures -eq 0 ]]; then echo "test_trial-merge: OK — all assertions passed."; else echo "test_trial-merge: FAILED — $failures assertion(s)."; exit 1; fi
