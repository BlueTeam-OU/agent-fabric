#!/usr/bin/env bash
# Claude Code PreToolUse hook on Bash, for every session: refuses a check
# piped into a filter and chained into a commit, a push or a merge.
#
# WHY. `check | tail -1 && git commit` tests tail's exit status, which is
# 0 whatever the check did, so a failed lint, suite or gate still commits,
# pushes or merges. A written rule did not hold: the coordinator did it six
# times, the last one pushing a red test to a pull request. A pipe followed
# by `;` is not refused (nothing is chained on it), nor a pipe no commit,
# push or merge follows.
#
# Output: a deny decision, or nothing. Exit 0 always; input it cannot
# parse is allowed silently — this is a fence against a habit, not a
# sandbox.
set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0
cmd="$(jq -r '.tool_input.command // empty' 2>/dev/null)" || exit 0
[[ -n "$cmd" ]] || exit 0
# One line: a continuation or a newline must not hide the chain.
flat="$(printf '%s' "$cmd" | tr '\n' ' ' | sed 's/\\ / /g')"
# Redirections carry an `&` the chain match must not stop at (`2>&1`,
# `&>log`), and `|&` is a pipe: normalise them away first (review of #54).
flat="$(sed -E 's/[0-9]*>&[0-9-]+/ /g; s/&>>?/>/g; s/\|&/|/g' <<<"$flat")"
# No exemption for pipefail: telling a `set -o pipefail` the shell runs from
# one in an echo, a comment or a subshell is a shell parser this hook is
# not, and each attempt left a bypass (review of #54). The way through is
# the one the message names: run the check, capture its status, commit on 0.
filter='(tail|head|grep|sed|cut|wc|awk|sort|uniq|tee)'
# Any global options between git and the subcommand (-C dir, -c k=v,
# --no-pager, --git-dir=…).
write='(git([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*[[:space:]]+(commit|push)|gh[[:space:]]+pr[[:space:]]+(merge|create))'
if grep -qE "\|[[:space:]]*${filter}\b[^;&]*&&.*\b${write}\b" <<<"$flat"; then
  jq -nc '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",
    permissionDecisionReason:"A check piped into a filter and chained with && into a commit, push or merge tests the filter'"'"'s exit status, not the check'"'"'s: a failed check would still commit. Run the check to a log, capture rc=$?, and commit only on 0."}}'
fi
exit 0
