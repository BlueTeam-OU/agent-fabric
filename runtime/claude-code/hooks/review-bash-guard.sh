#!/usr/bin/env bash
# runtime/claude-code/hooks/review-bash-guard.sh: the review class's Bash
# fence. The path is the contract (the code-review agent file's hook and
# subagent-clone-guard.sh call it, and bootstrap installs it user-scope
# beside its module); the fence, its rules and every reason for them are
# in review-bash-guard.py beside this file (ADR-040). Bash builtins only,
# to find it.
here="${BASH_SOURCE[0]%/*}"; [[ "$here" == "${BASH_SOURCE[0]}" ]] && here=.
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
# A guard that cannot run denies rather than allowing: the reviewer never
# NEEDS Bash to finish, and the failure mode of allowing is a push to the
# session's real branch.
if [[ ! -x "$py" || ! -f "$here/review-bash-guard.py" ]]; then
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"The review-class bash guard could not run (the fleet'"'"'s pinned Python or review-bash-guard.py is missing), so Bash is denied for the reviewer. Report without it."}}'
  exit 0
fi
# Not exec: a module that cannot load or dies exits non-zero with nothing on
# stdout, and the harness reads that as no objection. Any exit but 0 denies.
out="$("$py" "$here/review-bash-guard.py")" && { [[ -z "$out" ]] || printf '%s\n' "$out"; exit 0; }
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"The review-class bash guard failed while judging this command, so Bash is denied for it. Report without it."}}'
exit 0
