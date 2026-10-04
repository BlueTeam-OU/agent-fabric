#!/usr/bin/env bash
# Claude Code PreToolUse hook on Bash, scoped to the code-review agent
# (declared in runtime/claude-code/agents/code-review.md frontmatter,
# so it runs ONLY while that agent is active). bootstrap.sh installs it
# user-scope at ~/.claude/hooks/review-bash-guard.sh; the agent file
# looks in the launch project's .claude/ first, then there, so a review
# dispatched from projects/ or from any working copy finds its fence.
#
# WHY. The review class runs in the session's clone with no worktree,
# so the only thing between a reviewer and the session's branch is what
# it is allowed to run. Its charter says "read-only, no git writes" --
# a promise. This is the fence: under this project's permissions
# `git push` is auto-allowed and unprompted, so a reviewer that pushed
# would push the session's real branch. And a build that runs an
# install rewrites tracked lockfiles (pubspec.lock, pnpm-lock.yaml),
# which `git add -A` in the session would then commit. Both denied
# here whatever the prompt said. This is a fence against the ROUTINE
# path -- the git and install spellings an agent reaches for, in-place
# file writes and shell escapes -- not a sandbox: a determined
# `python3 -c` can still write. The charter is what governs the rest.
#
# Denies: printing the environment or secret material (below), and
# state-changing git (push, commit, add, rm, mv, checkout,
# switch, restore, reset, stash, rebase, merge, cherry-pick, revert,
# tag, branch creation/deletion, clean, worktree, am, apply, fetch,
# pull, remote and config changes, gc) and package installs/restores (pnpm/npm/
# yarn install|add|remove|update, flutter/dart pub get|add|upgrade,
# dotnet restore|add, pip install, cargo add). Allows everything else:
# read-only git, validators, guards, builds and tests that need no
# install (dotnet build/test --no-restore; pnpm --filter X test).
#
# Output: a deny decision, or nothing. Exit 0 always -- exit 2 would
# block; a guard that cannot parse its input allows and says nothing.
set -uo pipefail

# The reviewer never NEEDS Bash to finish, so a guard that cannot run
# denies rather than allowing -- the sibling dispatch guard asks; here
# the failure mode is a push to the session's real branch.
if ! command -v jq >/dev/null 2>&1; then
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"The review-class bash guard could not run (jq is not installed), so Bash is denied for the reviewer. Report without it."}}'
  exit 0
fi
cmd="$(jq -r '.tool_input.command // empty' 2>/dev/null)" || exit 0
[[ -n "$cmd" ]] || exit 0

GIT_WRITE='(^|[;&|(]|`)[[:space:]]*(sudo[[:space:]]+)?([^[:space:]]*/)?git([[:space:]]+-[A-Za-z-]+([[:space:]]+[^[:space:]]+)?)*[[:space:]]+(push|commit|add|rm|mv|checkout|switch|restore|reset|stash|rebase|merge|cherry-pick|revert|clean|am|apply|fetch|pull|gc|tag[[:space:]]+(-[adsfm]|--delete|--force|[A-Za-z0-9][^[:space:]]*)|worktree[[:space:]]+(add|remove|prune|move|lock|unlock|repair)|branch[[:space:]]+(-[dDmMc]|--delete|--move|--copy)|remote[[:space:]]+(add|remove|rm|rename|set-url)|config([[:space:]]+(--(local|worktree|global|system)|(-f|--file)[[:space:]]+[^[:space:]]+))*[[:space:]]+(set|unset|--add|--unset|--unset-all|--replace-all|--rename-section|--remove-section|--edit|-e|rename-section|remove-section|edit|[A-Za-z][A-Za-z0-9-]*\.[^[:space:]]+[[:space:]]+[^[:space:];&|-][^[:space:];&|]*))([[:space:]]|$|[);&|])'
INSTALL='(^|[;&|(]|`)[[:space:]]*(sudo[[:space:]]+)?((pnpm|npm|yarn)([[:space:]]+-[A-Za-z-]+)*[[:space:]]+(install|i|add|remove|rm|update|up|dedupe)([[:space:]]|$|[);&|])|(flutter|dart)[[:space:]]+pub[[:space:]]+(get|add|remove|upgrade|downgrade)([[:space:]]|$|[);&|])|dotnet[[:space:]]+(restore|add|remove)([[:space:]]|$|[);&|])|pip3?[[:space:]]+install([[:space:]]|$|[);&|])|cargo[[:space:]]+(add|install)([[:space:]]|$|[);&|]))'

# Secrets. Every account's shell carries its synced secrets in the
# environment (~/.bashrc sources secrets.env), so a reviewer listing its
# environment prints them into its transcript and the model's input:
# on 2026-10-04 one did, and the operator's signing key was rotated (#95).
# Denied in any command: the environment printed whole (env or printenv
# as a word with no command to run, bare set/export, declare -p/-x,
# os.environ / process.env / %ENV / ENVIRON / $ENV taken whole, BSD
# `ps e`), a secret-shaped name read (a $NAME expansion, ${!indirection},
# or environ/getenv/process.env/ENVIRON near a secret-shaped name), and
# secret material by path (secret*.env, .config/agent-fabric, the
# stores, .password-store, .gnupg, /proc/*/environ, gpg's secret export,
# pass, fabric-secrets store get). `env -i … cmd` stays allowed: it RUNS
# a command in a clean environment. A code SEARCH (grep, rg, git grep /
# log / show / diff / blame) may name these words as patterns and is
# refused only when it names a home, a hidden directory in one, or
# /proc as a path; the exemption covers that search alone, never what
# is chained or substituted into it. This is
# a fence for the routine spellings, not a sandbox: secret minimisation
# (keeping a secret out of the session's environment) is the control.
W='(^|[^[:alnum:]_.-])'
ENV_PRINT="${W}"'\\?(env|printenv)([[:space:]]+(-[uC][[:space:]]+[^[:space:]]+|-[A-Za-z0-9-]+|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*))*[[:space:]]*($|[;&|)<>'"'"'"`])|'"${W}"'printenv([^[:alnum:]_.-]|$)|(^|[;&|(]|`)[[:space:]]*set[[:space:]]*($|[;&|)])|(^|[;&|(]|`)[[:space:]]*(export|declare|typeset)[[:space:]]*($|[;&|)])|(export|declare|typeset)[[:space:]]+-[a-zA-Z]*[px]|compgen[[:space:]]+-[a-zA-Z]*[ev]|os\.environ($|[^.[A-Za-z0-9_]|\.(copy|items|keys|values|__))|process\.env($|[^.[A-Za-z0-9_])|%ENV|ENVIRON($|[^[A-Za-z0-9_])|\$ENV($|[^A-Za-z0-9_])|'"${W}"'ps([[:space:]]+-[^[:space:]]+)*[[:space:]]+[a-zA-Z]*e[a-zA-Z]*([[:space:];|&]|$)'
SECRET_NAME='(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|_KEY)'
SECRET_VAR='\$\{?[A-Za-z0-9_]*'"$SECRET_NAME"'|\$\{!|(environ|getenv|process\.env|ENVIRON|%ENV|\$ENV)[^;|&]{0,60}'"$SECRET_NAME"
SECRET_PATH='secrets?[^[:space:]/]*\.env|\.config/agent-fabric|agent-fabric/(secrets|children)|\.password-store|\.gnupg|/proc/[^[:space:]]*/environ|--export-secret|(^|[;&|(]|`)[[:space:]]*pass[[:space:]]+(show|ls|find|grep|otp)|(fabric-secrets|secret_store\.py)[[:space:]]+(store[[:space:]]+)?(get|show|export-key|bundle|child-bundle)'
# A search's PATH, as opposed to its pattern: a home itself or anything
# under one of its hidden directories (~/.config, ~/.local/share, the
# stores, .gnupg), the same reached by climbing out of the clone
# (../../.config), /, /home and /root as roots, and anything in /proc.
HOME_PATH='(~|\$HOME|\$\{HOME\}|/home/[^/[:space:]"'"'"']+|/root)(/\.[^/[:space:]"'"'"']+(/[^[:space:]"'"'"']*)?)?/?([[:space:]"'"'"';&|)]|$)|(^|[[:space:]"'"'"'=])(\.\./)+\.[^/[:space:]"'"'"']+|(^|[[:space:]"'"'"'=])/(home|root|proc)?/?([[:space:]"'"'"';&|)]|$)|(^|[[:space:]"'"'"'=])/proc(/[^[:space:]]*)?([[:space:]"'"'"';&|)]|$)|/proc/[^[:space:]]*/environ'
SEARCH='^[[:space:]]*(grep|egrep|fgrep|rg|ag|git([[:space:]]+-[A-Za-z]+([[:space:]]+[^[:space:]]+)?)*[[:space:]]+(grep|log|show|diff|blame))([[:space:]]|$)'

# Shell escapes that would carry any of the above past a string match,
# and the routine in-place file writes. Redirections are allowed only
# to /dev/null (the reviewer's own quieting) or to another fd.
# Also what makes an allowed tool run a program the guard never sees:
# git's one-shot config (-c / --config-env: diff.external, core.pager),
# a GIT_*, PAGER or EDITOR assignment, rg --pre, find -exec / -ok.
ESCAPE='(^|[;&|(]|`)[[:space:]]*(sudo[[:space:]]+)?(eval|exec|(ba|z|da|k)?sh[[:space:]]+-[a-zA-Z]*c)([[:space:]]|$)|(^|[^[:alnum:]_.-])git([[:space:]]+(-C[[:space:]]+[^[:space:]]+|--[a-z-]+(=[^[:space:]]+)?|-[pP]))*[[:space:]]+(-c|--config-env)([[:space:]=]|[A-Za-z])|(^|[;&|(`[:space:]])(GIT_[A-Z0-9_]+|PAGER|LESSOPEN|LESSCLOSE|EDITOR|VISUAL)=|[[:space:]]--pre([[:space:]=]|$)|[[:space:]]-(exec|execdir|ok|okdir)([[:space:]]|$)'
WRITE='(^|[;&|(]|`)[[:space:]]*(sudo[[:space:]]+)?(sed[[:space:]]+(-[a-zA-Z]*i|--in-place)|tee|rm|mv|cp|truncate|chmod|chown|ln|install|patch|rsync)([[:space:]]|$)'
stripped="$(printf '%s' "$cmd" | sed -E 's/[0-9]*>&[0-9-]*//g; s/>>?[[:space:]]*\/dev\/null//g')"

reason=""
secret=""
# The search exemption is per segment: a command is cut at ; & | and
# newlines, and only a segment that IS a search, with no substitution
# inside it, is judged by the search rule; every other segment by the
# full one. Cut naively, so a | inside a quoted pattern may refuse a
# search, never admit a command (an exemption over the whole command
# let `grep x f; env` through: #96 round 2).
segments="$(printf '%s\n' "$cmd" | sed -E 's/(\|\||&&|[;&|])/\n/g')"
while IFS= read -r seg; do
  if printf '%s\n' "$seg" | grep -qE "$SEARCH" && ! printf '%s\n' "$seg" | grep -qE '\$\(|`|[<>]\('; then
    printf '%s\n' "$seg" | grep -qE "$HOME_PATH|$SECRET_VAR" && secret=1
  elif printf '%s\n' "$seg" | grep -qE "$ENV_PRINT|$SECRET_VAR|$SECRET_PATH"; then
    secret=1
  fi
done <<<"$segments"
# The cut loses the separators some patterns anchor on; the whole
# command still answers to them unless a segment was a search.
if [[ -z "$secret" ]] && ! printf '%s\n' "$segments" | grep -qE "$SEARCH" \
   && printf '%s\n' "$cmd" | grep -qE "$ENV_PRINT|$SECRET_VAR|$SECRET_PATH"; then
  secret=1
fi
if [[ -n "$secret" ]]; then
  reason="The review class may not print the environment, expand a secret-shaped variable, or read secret material (secrets.env, the stores, gpg keys, /proc/*/environ): every account's environment carries its credentials, and what you print enters the transcript. Describe a secret by its name and shape only. To run a check in a clean environment, use env -i NAME=value … command."
elif printf '%s\n' "$cmd" | grep -qE "$ESCAPE"; then
  reason="The review class may not use shell escapes (eval, exec, sh -c): they carry a write past this guard. Run the command directly."
elif printf '%s\n' "$cmd" | grep -qE "$WRITE" || printf '%s\n' "$stripped" | grep -q '>'; then
  reason="The review class runs in the session clone and is READ-ONLY: no in-place edits, no file writes, no redirection except to /dev/null. Report what you would have changed instead."
elif printf '%s\n' "$cmd" | grep -qE "$GIT_WRITE"; then
  reason="The review class runs in the session clone and is READ-ONLY: no state-changing git (push, commit, checkout, reset, stash, ...). Read-only history (log, show, diff, blame) is expected of you. Report what you would have changed instead."
elif printf '%s\n' "$cmd" | grep -qE "$INSTALL"; then
  reason="The review class may not run installs or restores (pub get, pnpm install, dotnet restore, ...): they rewrite tracked lockfiles in the session clone. Build and test only with what is already restored (dotnet build/test --no-restore, pnpm --filter <app> test), or say the check needs an install and skip it."
fi
[[ -n "$reason" ]] || exit 0
jq -nc --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
exit 0
