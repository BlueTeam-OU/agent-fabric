#!/usr/bin/env bash
# runtime/claude-code/hooks/agent-dispatch-guard.sh — the PreToolUse hook for
# the Agent tool. The path is the contract (workspace/settings.json runs it);
# the rules, their incidents and the contract are in
# tools/fabric/guards/dispatch_guard.py (ADR-040 §5 rule 4).
#
# A permission gate that cannot run must not vanish into an allow: the
# harness reads a failed hook as no objection. So this shim does not exec:
# with no python3 on PATH, a module that is not where it should be, or a
# run that fails, it ASKS, and the person at the keyboard sees why. Bash
# builtins only, so nothing it needs can be missing.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
module="$here/../../../tools/fabric/guards/dispatch_guard.py"
cannot_run() {
  printf '%s\n' "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"The dispatch guard could not run ($1). Approve only if you have checked model and isolation yourself. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).\"}}"
  exit 0
}
command -v python3 >/dev/null 2>&1 || cannot_run "python3 is not on PATH"
[[ -x /usr/bin/python3 ]] || cannot_run "/usr/bin/python3 is missing"
[[ -f "$module" ]] || cannot_run "its module is not beside it"
# -I: no PYTHONPATH or user site can put a module of its own under a
# permission gate; -S: no site import, which the stdlib-only guard never
# needs (a few milliseconds on every dispatch).
out="$(/usr/bin/python3 -I -S "$module" 2>/dev/null)" || cannot_run "the guard failed"
[[ -z "$out" ]] || printf '%s\n' "$out"
exit 0
