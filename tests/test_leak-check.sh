#!/usr/bin/env bash
# tests/test_leak-check.sh — the leak check names what a run added and
# nothing else, whole names included.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=leak-check.sh
. "$HERE/leak-check.sh"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ✓ %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  ✗ %s\n' "$1"; [[ -n "${2:-}" ]] && printf '%s\n' "$2" | sed 's/^/      /'; }
SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT
mkdir "$SANDBOX/existing" "$SANDBOX/node-compile-cache"
snap="$(leak_snapshot "$SANDBOX")"

echo "nothing added"
out="$(leak_report "$SANDBOX" "$snap")"; rc=$?
[[ $rc -eq 0 && -z "$out" ]] && ok "a run that added nothing passes silently" || bad "clean run" "$out"

echo "entries added"
mkdir "$SANDBOX/agentd-home-x1" "$SANDBOX/a b" "$SANDBOX/star*.py"
touch "$SANDBOX/a b/inner" "$SANDBOX/existing/inner-is-not-top-level"
out="$(cd "$HERE" && leak_report "$SANDBOX" "$snap")"; rc=$?
[[ $rc -eq 1 ]] && ok "a run that added entries fails" || bad "rc" "$out"
grep -qx '   agentd-home-x1' <<<"$out" && ok "the added directory is named" || bad "name" "$out"
grep -qx '   a b' <<<"$out" && ok "a name with a space is one entry" || bad "space" "$out"
grep -qx '   star\*.py' <<<"$out" && ok "a glob character is printed, not expanded" || bad "glob" "$out"
grep -q 'existing' <<<"$out" && bad "a pre-existing entry was reported" "$out" || ok "pre-existing entries are never reported"
[[ "$(grep -c '^   ' <<<"$out")" == 3 ]] && ok "exactly the three added entries" || bad "count" "$out"

echo "the directory"
[[ "$(TMPDIR=/x/y leak_dir)" == /x/y ]] && ok "TMPDIR first" || bad "TMPDIR"
[[ "$(env -u TMPDIR TMP=/t bash -c '. "'"$HERE"'/leak-check.sh"; leak_dir')" == /t ]] && ok "then TMP" || bad "TMP"
[[ "$(env -u TMPDIR -u TMP -u TEMP bash -c '. "'"$HERE"'/leak-check.sh"; leak_dir')" == /tmp ]] && ok "then /tmp" || bad "/tmp"

echo "run.sh uses it, on a directory of its own"
grep -q 'leak-check.sh' "$HERE/run.sh" && grep -q 'leak_report' "$HERE/run.sh" && ok "run.sh sources the check and reports with it" || bad "run.sh wiring"
grep -q 'export TMPDIR="\$SCRATCH_DIR"' "$HERE/run.sh" && ok "the run exports its own TMPDIR, so a concurrent writer is never a leak" || bad "TMPDIR export"

echo "a run killed by a signal ENDS, and its directory goes with it"
# Behaviour, not text: a trap that removed the directory and let the
# script carry on passed a grep for its own line while every remaining
# suite ran against a deleted TMPDIR. Here run.sh's static group is
# started in its own process group with a shellcheck that blocks, the
# group gets TERM, and the run must be gone within seconds with no
# af-t.* left under the directory it was made in (XDG_RUNTIME_DIR here).
FAKEBIN="$SANDBOX/bin"; mkdir -p "$FAKEBIN"
printf '#!/usr/bin/env bash\nsleep 30\n' > "$FAKEBIN/shellcheck"; chmod +x "$FAKEBIN/shellcheck"
RUNTMP="$SANDBOX/runtmp"; mkdir -p "$RUNTMP"
before="$(ls -A "$RUNTMP")"
# run.sh makes af-t.* under XDG_RUNTIME_DIR (short_dir), so the test
# points that at its sandbox.
XDG_RUNTIME_DIR="$RUNTMP" PATH="$FAKEBIN:$PATH" setsid bash "$HERE/run.sh" static > "$SANDBOX/run.out" 2>&1 &
RUNPID=$!
made_dir() { compgen -G "$RUNTMP/af-t.*" >/dev/null; }
for _ in $(seq 100); do made_dir && break; sleep 0.1; done
made_dir && ok "the run made its directory under XDG_RUNTIME_DIR" || bad "run directory" "$(ls -A "$RUNTMP")"
kill -TERM -- "-$RUNPID" 2>/dev/null || kill -TERM "$RUNPID"
ended=0
for _ in $(seq 50); do kill -0 "$RUNPID" 2>/dev/null || { ended=1; break; }; sleep 0.1; done
(( ended )) && ok "TERM ends the run within five seconds" || { bad "the run outlived TERM" "$(cat "$SANDBOX/run.out")"; kill -KILL -- "-$RUNPID" 2>/dev/null; }
wait "$RUNPID" 2>/dev/null; rc=$?
[[ $rc -eq 143 ]] && ok "and it exits 143, the conventional status" || bad "exit status $rc" "$(cat "$SANDBOX/run.out")"
[[ "$(ls -A "$RUNTMP")" == "$before" ]] && ok "and its directory is gone" || bad "directory left" "$(ls -A "$RUNTMP")"
grep -q "suite(s) FAILED" "$SANDBOX/run.out" && bad "the interrupted run was reported as suite failures" "$(cat "$SANDBOX/run.out")" || ok "the interrupted run reports no suite failures"

echo "a run killed by a group KILL leaves no directory and no process"
# KILL runs no trap: the directories go by the watcher run.sh starts.
RUNTMP2="$SANDBOX/runtmp2"; mkdir -p "$RUNTMP2"
XDG_RUNTIME_DIR="$RUNTMP2" PATH="$FAKEBIN:$PATH" setsid bash "$HERE/run.sh" static > "$SANDBOX/run2.out" 2>&1 &
KPID=$!
for _ in $(seq 100); do compgen -G "$RUNTMP2/af-t.*" >/dev/null && break; sleep 0.1; done
compgen -G "$RUNTMP2/af-t.*" >/dev/null || bad "KILL case: no run directory" "$(ls -A "$RUNTMP2")"
kill -KILL -- "-$KPID" 2>/dev/null
wait "$KPID" 2>/dev/null
for _ in $(seq 50); do [[ -z "$(ls -A "$RUNTMP2")" ]] && break; sleep 0.1; done
[[ -z "$(ls -A "$RUNTMP2")" ]] && ok "a group KILL leaves no directory behind" || bad "directory left after KILL" "$(ls -A "$RUNTMP2")"
if pgrep -g "$KPID" >/dev/null; then bad "processes left in the killed group" "$(pgrep -g "$KPID" -a)"; pkill -KILL -g "$KPID"; else ok "and no process of the group survives"; fi

echo; echo "leak-check: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
