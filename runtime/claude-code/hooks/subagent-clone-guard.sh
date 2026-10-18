#!/usr/bin/env bash
# runtime/claude-code/hooks/subagent-clone-guard.sh
#
# Claude Code PreToolUse hook on Write / Edit / MultiEdit / NotebookEdit /
# Bash: a capability-class subagent running in the SESSION CLONE is
# read-only.
#
# WHY. Where a subagent runs is what tells a writer from a reader. Every
# writing dispatch carries isolation worktree and works under
# .claude/worktrees/ — the dispatch guard (agent-dispatch-guard.sh)
# refuses one that does not — and the one class that runs unisolated in
# the clone is the review class, whose agent file lists no writing tool
# and fences its Bash (review-bash-guard.sh). That leaves the dispatches
# the dispatch guard never sees: an agent() call inside a Workflow script
# (its tool input is script text, and both fields default the wrong
# way — isolation to the clone), and a launch that resolves a class
# natively rather than through the Agent tool. This hook is the
# backstop at the point of the write: a class subagent whose cwd is not
# under .claude/worktrees/ may not write, and its Bash gets the review
# fence (no state-changing git, no installs, no shell escapes, no
# redirection into the tree). For the review class it duplicates what
# the agent file already says; for everything else it is the only fence.
#
# SCOPE, deliberately narrow: only when the hook input carries an
# agent_id (a subagent — the main session is never touched) AND the
# agent_type is one this control plane dispatches (the three classes,
# the reviewer, and the harness built-ins a class-less call would have
# named). A fork continues the session and may write in the clone by
# design; an unknown type is left alone rather than guessed at.
#
# Verified on Claude Code 2.1.270: a subagent's tool call carries
# agent_id, agent_type and cwd in the hook input, and a worktree-isolated
# subagent reports <repo>/.claude/worktrees/agent-<id> as cwd. Whether a
# Workflow-spawned agent carries the same fields has not been observed
# live; the hook allows when they are absent, so it fails open there,
# not closed.
#
# Output: a deny decision, an ask when the guard itself cannot run, or
# nothing; for Bash, the review fence's answer passed through, which lets a
# command through rewritten to run with a clean environment (no secret
# inherited, the session markers kept), so every unisolated subagent's Bash
# runs that way, not the review class's alone. Exit 0 always — exit 2 would block; a guard that cannot parse
# its input allows and says nothing.
set -uo pipefail

HERE="${BASH_SOURCE[0]%/*}"; [[ "$HERE" != "${BASH_SOURCE[0]}" ]] || HERE=.

# A permission gate that cannot run must not vanish into an allow.
if ! command -v jq >/dev/null 2>&1; then
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"The subagent clone guard could not run (jq is not installed). Approve only if this tool call is not a subagent writing in the session clone. See CLAUDE.md - Subagents."}}'
  exit 0
fi

input="$(cat)"
read -r agent_id agent_type tool cwd < <(printf '%s' "$input" | jq -r '[(.agent_id // ""), (.agent_type // ""), (.tool_name // ""), (.cwd // "")] | map(if . == "" then "-" else . end) | join(" ")' 2>/dev/null) || exit 0

[[ "${agent_id:-}" != "-" && -n "${agent_id:-}" ]] || exit 0   # the main session, or unparsable
case "$agent_type" in
  code-low|code-medium|code-high|code-plan|code-review|general-purpose|claude|Explore|Plan) ;;
  *) exit 0 ;;                                            # a fork, or a type this control plane does not dispatch
esac
[[ "$cwd" != */.claude/worktrees/* ]] || exit 0           # isolated: it may write there

# Why a writing class is here at all, said in every refusal it gets. Seen live
# (2026-10-18, a code-low agent dispatched with isolation worktree): resumed by
# SendMessage, it ran in the session clone on the session's branch, its
# worktree gone; Claude Code does not restore a resumed subagent's isolation.
# The fence is then right, and the review fence's own words ("The review
# class ...") told a code-medium agent nothing (j228). Whether a resumed agent
# whose worktree held changes gets it back was not observed.
why() {
  printf 'This %s subagent runs in the session clone (%s), not in a worktree of its own, so it is read-only here. A subagent resumed by SendMessage runs here: its isolation is not restored. Do not resume a writing agent: dispatch a new one with isolation worktree for the next step, or report what you would have changed.' "$agent_type" "$cwd"
}
case "$tool" in
  Bash)
    out="$(printf '%s' "$input" | bash "$HERE/review-bash-guard.sh")"
    if [[ "$agent_type" != code-review ]] && printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
      out="$(printf '%s' "$out" | jq -c --arg why "$(why)" '.hookSpecificOutput.permissionDecisionReason |= $why + " The read-only fence says: " + .')"
    fi
    printf '%s' "$out" ;;
  Write|Edit|MultiEdit|NotebookEdit)
    if [[ "$agent_type" == code-review ]]; then
      reason="The review class runs in the session clone and is read-only: it may not use $tool. Report the finding instead of editing. See CLAUDE.md - Subagents."
    else
      reason="$(why) It may not use $tool. See CLAUDE.md - Subagents."
    fi
    jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}' ;;
  *) ;;                                                   # not a tool this hook is matched on
esac
