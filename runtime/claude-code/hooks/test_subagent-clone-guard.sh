#!/usr/bin/env bash
# runtime/claude-code/hooks/test_subagent-clone-guard.sh
#
# Behavioural tests for subagent-clone-guard.sh.
#
# What this holds still: a capability-class subagent whose cwd is the
# session clone (not a worktree) may not write and gets the review Bash
# fence; the main session, a fork, an unknown type and an isolated
# subagent are untouched; a guard that cannot run asks rather than
# allows. Every case pipes a hook payload through the REAL script and
# checks the decision.
#
# Exit codes: 0 all assertions passed; 1 one or more failed
set -uo pipefail
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/subagent-clone-guard.sh"
[[ -f "$UNDER_TEST" ]] || { echo "test: not found: $UNDER_TEST" >&2; exit 1; }
[[ -f "$SCRIPT_DIR/review-bash-guard.sh" ]] || { echo "test: the review Bash fence must sit beside the guard" >&2; exit 1; }
failures=0
pass() { echo "  ok   $1"; }
fail() { echo "  FAIL $1" >&2; [[ $# -gt 1 ]] && printf '       %s\n' "$2" >&2; failures=$((failures + 1)); }
CLONE="${TMPDIR:-/tmp}/fixture-clone"; WT="$CLONE/.claude/worktrees/agent-abc"

# decision <tool> <agent_type|-> <cwd> [command] -> allow | deny | ask | malformed
# (a command rewritten to run with a clean environment, and no decision, is an allow)
decision() {
  local tool="$1" type="$2" cwd="$3" cmd="${4:-}" out payload
  if [[ "$type" == "-" ]]; then
    payload=$(jq -nc --arg t "$tool" --arg c "$cwd" --arg m "$cmd" '{tool_name:$t,cwd:$c,tool_input:{command:$m}}')
  else
    payload=$(jq -nc --arg t "$tool" --arg a "$type" --arg c "$cwd" --arg m "$cmd" '{tool_name:$t,agent_id:"a1",agent_type:$a,cwd:$c,tool_input:{command:$m}}')
  fi
  out="$(printf '%s' "$payload" | bash "$UNDER_TEST" 2>/dev/null)"
  if [[ -z "$out" ]]; then echo allow; else printf '%s' "$out" | jq -r '.hookSpecificOutput | .permissionDecision // (if .updatedInput then "allow" else "malformed" end)'; fi
}
expect() {
  local label="$1" want="$2"; shift 2
  local got; got="$(decision "$@")"
  if [[ "$got" == "$want" ]]; then pass "$label"; else fail "$label" "want $want, got $got"; fi
}

echo "clone guard: the main session is never touched"
expect "Write with no agent_id is allowed" allow Write - "$CLONE"
expect "Bash git push with no agent_id is allowed (the session's own rules apply)" allow Bash - "$CLONE" "git push"

echo "clone guard: a class subagent in the session clone may not write"
for t in code-low code-medium code-high code-plan code-review general-purpose claude Explore Plan; do
  expect "$t: Write in the clone is denied" deny Write "$t" "$CLONE"
done
for tool in Edit MultiEdit NotebookEdit; do
  expect "$tool in the clone is denied" deny "$tool" code-medium "$CLONE"
done

echo "clone guard: its Bash gets the review fence"
expect "git push in the clone is denied" deny Bash code-high "$CLONE" "git push origin x"
expect "git commit in the clone is denied" deny Bash code-low "$CLONE" "git commit -m x"
expect "pnpm install in the clone is denied" deny Bash code-high "$CLONE" "pnpm install"
expect "redirection into the tree is denied" deny Bash code-medium "$CLONE" "echo x > notes.md"
expect "git log in the clone is allowed (read-only)" allow Bash code-high "$CLONE" "git log --oneline -3"
expect "git diff in the clone is allowed (read-only)" allow Bash code-low "$CLONE" "git diff main..HEAD"

echo "clone guard: isolated in a worktree, the same subagent may write"
expect "Write in a worktree is allowed" allow Write code-high "$WT"
expect "Bash git add in a worktree is allowed (isolation is the fence there)" allow Bash code-low "$WT" "git add -A"
expect "a worktree path nested deeper still counts" allow Write code-medium "$WT/apps/x"

echo "clone guard: types this control plane does not dispatch are left alone"
expect "a fork writing in the clone is allowed" allow Write fork "$CLONE"
expect "an unknown custom type writing in the clone is allowed" allow Write some-other-agent "$CLONE"

echo "clone guard: a tool it is not matched on passes through"
expect "Read in the clone is allowed" allow Read code-high "$CLONE"
expect "Grep in the clone is allowed" allow Grep code-high "$CLONE"

echo "clone guard: the denial says why"
out="$(printf '{"tool_name":"Write","agent_id":"a1","agent_type":"code-high","cwd":"%s","tool_input":{}}' "$CLONE" | bash "$UNDER_TEST")"
if grep -q "session clone" <<<"$out" && grep -q "isolation worktree" <<<"$out"; then pass "names the clone and the worktree rule"; else fail "names the clone and the worktree rule" "$out"; fi

echo "clone guard: a guard that cannot run asks; it never silently allows"
# jq is the one dependency; an empty PATH removes it. The guard checks
# for jq before it runs anything else, so nothing else is needed from
# PATH before the ask is printed (bash itself is invoked by path).
out="$(printf '{"tool_name":"Write","agent_id":"a1","agent_type":"code-high","cwd":"%s","tool_input":{}}' "$CLONE" | env PATH=/nonexistent /bin/bash "$UNDER_TEST" 2>/dev/null)"
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "ask"' >/dev/null 2>&1; then pass "with jq unavailable the guard asks"; else fail "with jq unavailable the guard asks" "[$out]"; fi

echo "clone guard: malformed input never exits 2"
for payload in '{}' 'not json' ''; do
  out="$(printf '%s' "$payload" | bash "$UNDER_TEST" 2>/dev/null)"; rc=$?
  if [[ "$rc" -ne 2 ]]; then pass "payload (${payload:-empty}) rc=$rc"; else fail "payload (${payload:-empty}) exited 2" "$out"; fi
done

echo
if [[ "$failures" -eq 0 ]]; then echo "test_subagent-clone-guard: OK — all assertions passed."; exit 0; fi
echo "test_subagent-clone-guard: FAILED — $failures assertion(s) failed." >&2; exit 1
