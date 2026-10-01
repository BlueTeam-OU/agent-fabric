#!/usr/bin/env bash
# runtime/claude-code/hooks/agent-dispatch-guard.sh — the PreToolUse hook for
# the Agent tool. The path is the contract (workspace/settings.json runs it);
# the rules, their incidents and the contract are in
# tools/fabric/guards/dispatch_guard.py (ADR-040 §5 rule 4).
#
# A permission gate that cannot run must not vanish into an allow: the
# harness reads a failed hook as no objection. So this shim does not exec:
# with the fleet's pinned Python missing, a module that is not where it
# should be, or a run that fails, it ASKS, and the person at the keyboard
# sees why. Bash builtins only, so nothing it needs can be missing.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
module="$here/../../../tools/fabric/guards/dispatch_guard.py"
cannot_run() {
  printf '%s\n' "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"The dispatch guard could not run ($1). Approve only if you have checked model and isolation yourself. See the subagent-dispatch skill (agent-fabric policies/subagent-dispatch/SKILL.md).\"}}"
  exit 0
}
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || cannot_run "the fleet's pinned Python is missing ($py)"
[[ -f "$module" ]] || cannot_run "its module is not beside it"
# -I: no PYTHONPATH or user site can put a module of its own under the
# guard; the routing probe it starts under a fabric launch runs -E -s for
# the same reason (the module says why not -I). -S: no site import, which
# the stdlib-only guard never needs.
out="$("$py" -I -S "$module" 2>/dev/null)" || cannot_run "the guard failed"
[[ -z "$out" ]] || printf '%s\n' "$out"
exit 0
