#!/usr/bin/env bash
# runtime/claude-code/hooks/model-switch-guard.sh — the PreModelSwitch hook. The path is the contract (the
# settings files run it by path); the guard, its contract and every reason for it are in
# model-switch-guard.py beside this file (ADR-040 §5 rule 1, Wave 9 batch 5).
#
# A permission gate that cannot run must not vanish into an allow: the harness reads a failed hook as no
# objection. So this forwarder does not exec: with the fleet's pinned Python missing, its module not beside
# it, or a run that fails, it ASKS, in a vanilla session too. Bash builtins only, so nothing it needs can be
# missing.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
module="$here/model-switch-guard.py"
cannot_run() {
  printf '%s\n' "{\"hookSpecificOutput\":{\"hookEventName\":\"PreModelSwitch\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"The model-switch guard could not run ($1). In a broker session a bare model id runs without its family shim; approve only if the target is a composite or a family that needs none.\"}}"
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
