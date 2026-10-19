#!/usr/bin/env bash
# runtime/claude-code/hooks/subagent-clone-guard.sh — the PreToolUse hook on Write, Edit, MultiEdit,
# NotebookEdit and Bash that makes a class subagent in the session clone read-only. The path is the contract
# (the settings files run it by path); the guard, its contract and every reason for it are in
# subagent-clone-guard.py beside this file (ADR-040 §5 rule 1, Wave 9 batch 5).
#
# A permission gate that cannot run must not vanish into an allow: the harness reads a failed hook as no
# objection. So this forwarder does not exec: with the fleet's pinned Python missing, its module not beside
# it, or a run that fails, it ASKS. Bash builtins only, so nothing it needs can be missing.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
module="$here/subagent-clone-guard.py"
cannot_run() {
  printf '%s\n' "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"The subagent clone guard could not run ($1). Approve only if this tool call is not a subagent writing in the session clone. See CLAUDE.md - Subagents.\"}}"
  exit 0
}
# The fleet's pinned Python (runtime/python.json), by its fixed path and never AGENT_FABRIC_PYTHON: a gate
# whose interpreter the environment chose could be pointed at /bin/true (as agent-dispatch-guard.sh).
py=/usr/local/bin/fabric-python
[[ -x "$py" ]] || cannot_run "the fleet's pinned Python is missing ($py)"
[[ -f "$module" ]] || cannot_run "its module is not beside it"
# -I: no PYTHONPATH or user site can put a module of its own under the guard; -S: no site import.
out="$("$py" -I -S "$module" 2>/dev/null)" || cannot_run "the guard failed"
[[ -z "$out" ]] || printf '%s\n' "$out"
exit 0
