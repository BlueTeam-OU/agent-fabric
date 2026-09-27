#!/usr/bin/env bash
# Behavioural tests for runtime/claude-code/hooks/pipe-status-guard.sh:
# a check piped into a filter and then chained into a commit, a push or a
# merge is refused, because the chain tests the filter's exit status, not
# the check's; the same command with the status captured, and a pipe that no
# commit follows, are allowed; pipefail is no exemption, since a hook cannot
# tell one the shell runs from one in an echo or a comment.
#
# Exit codes: 0 all assertions passed; 1 one or more failed.
set -uo pipefail
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/pipe-status-guard.sh"
[[ -f "$UNDER_TEST" ]] || { echo "test: not found: $UNDER_TEST" >&2; exit 1; }
failures=0
pass() { echo "  ok   $1"; }
fail() { echo "  FAIL $1" >&2; [[ $# -gt 1 ]] && printf '       %s\n' "$2" >&2; failures=$((failures + 1)); }
decision() {
  local out; out="$(jq -nc --arg c "$1" '{tool_name:"Bash",tool_input:{command:$c}}' | bash "$UNDER_TEST" 2>/dev/null)"
  if [[ -z "$out" ]]; then echo allow; else printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // "malformed"'; fi
}
expect() { local got; got="$(decision "$3")"; if [[ "$got" == "$2" ]]; then pass "$1"; else fail "$1" "want $2, got $got for: $3"; fi; }

echo "a filtered check chained into a commit, a push or a merge is refused"
for c in 'python3 tests/test_adr.py | tail -1 && git commit -q -m x' \
         'bash tests/run.sh 2>&1 | tail -3 && git add -A && git commit -m y' \
         'lint | grep -q clean && git push -q origin HEAD' \
         'python3 t.py | head -5 && git -C /repo commit -m z' \
         'check | tail -1 && gh pr merge 53 --merge' \
         $'python3 t.py \\\n  | tail -1 \\\n  && git commit -m multi' \
         'set +o pipefail; false | tail -1 && git commit -m bad' \
         'echo pipefail; check | tail -1 && git commit -m bad' \
         'check | tail -1 && git commit -m "pipefail"' \
         'set -o pipefail; set +o pipefail; x | tail -1 && git push' \
         'set -o pipefail; python3 t.py | tail -1 && git commit -m x' \
         'echo set -o pipefail; false | tail -1 && git commit -m x' \
         $'# set -o pipefail\nfalse | tail -1 && git commit -m x' \
         '( set -o pipefail ); false | tail -1 && git commit -m x' \
         'check | tail -3 2>&1 && git commit -m x' \
         'check |& tail -3 && git commit -m x' \
         'check | grep -q ok >/dev/null 2>&1 && git push' \
         'check | tail -1 &> log && git commit' \
         'check | tail -1 && git --no-pager commit -m x' \
         'check 2>&1 | tail -1 && git -c core.hooksPath=x commit -m x' \
         'check | tail -1 >& log && git commit -m x' \
         'check | tail -1 >&log && git commit -m x' \
         'check | tail -1 2>& 1 && git push' \
         'check | tail -1 <&0 && git commit -m x' \
         'echo "note: set -o pipefail"; false | tail -1 && git commit -m x' \
         'check | tail -1 && git -C "my dir" commit -m x'; do
  expect "refused: $c" deny "$c"
done

echo "the status captured, or no commit after the pipe: allowed"
for c in 'python3 t.py > log 2>&1; rc=$?; [ $rc -eq 0 ] && git commit -m x' \
         'git log --oneline | head -3' \
         'grep -q x file && git commit -m y' \
         'python3 t.py | tail -1; echo done' \
         'git commit -q -m "a message | tail with a pipe in it"' \
         'git status --short | head; git push -q origin HEAD'; do
  expect "allowed: $c" allow "$c"
done

echo "a malformed input allows and says nothing"
out="$(printf 'not json' | bash "$UNDER_TEST" 2>/dev/null)"; [[ -z "$out" ]] && pass "malformed: silent allow" || fail "malformed input" "$out"

if (( failures > 0 )); then echo "test_pipe-status-guard: $failures assertion(s) FAILED"; exit 1; fi
echo "test_pipe-status-guard: all assertions passed"
