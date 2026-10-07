#!/usr/bin/env bash
# Claude Code status line: [harness version · model · effort] · agent@host · pull request · working copy · git branch.
#
# The AGENT is the Linux login, from agent-fabric's canonical resolver
# (bin/fabric-whoami); the directory is shown as the working copy the
# session is in — context, never identity. Reads the session JSON on
# stdin; runs locally, no API tokens. Wired by the workspace
# .claude/settings.json `statusLine` that runtime/claude-code/bootstrap.sh
# writes.
input=$(cat)

FABRIC_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../.." && pwd)"
dir=$(printf '%s' "$input" | jq -r '.workspace.current_dir // empty')
[ -z "$dir" ] && dir="$PWD"
model=$(printf '%s' "$input" | jq -r '.model.display_name // "Claude"')
# THE HARNESS BRACKET (owner, 2026-09-24): the Claude Code version (the
# bare number — the owner asked for no product name before it), the
# model and the session's live effort level, in that order — the three
# things that decide how this session thinks, readable at a glance and
# comparable across sessions (a session that reads "high" beside another's
# "medium" is a routing question; routing/effort.json says what each class
# asks for). Both are read from the session JSON, never from the
# environment: `version` is the harness's own; `effort` is optional in
# that JSON — present only when the model takes an effort level — so a
# model that expresses none shows NO level rather than an invented one,
# and an older harness that sends no version shows the model alone.
version=$(printf '%s' "$input" | jq -r '.version // empty')
effort=$(printf '%s' "$input" | jq -r '.effort.level // empty')
harness="$model"
[ -z "$version" ] || harness="$version · $harness"
[ -z "$effort" ] || harness="$harness · $effort"
agent=$("$FABRIC_ROOT/bin/fabric-whoami" 2>/dev/null || id -un)
host=$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo "?")
wc=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)
wc=${wc:+$(basename "$wc")}
# The ref segment exists only inside a repository, and its icon says
# which state it is: 🌿 a branch (an unborn one still has its name);
# 🔗 a detached HEAD, with its short SHA — a link straight to a commit, not a branch (owner,
# 2026-09-15). Outside a repository — the parent projects/ workspace, by
# design — there is no segment at all. It used to print "🌿 detached" for
# both a detached HEAD and no repository, and a session launched from
# projects/ read as sitting on a branch nobody had made.
ref=""
if [ -n "$wc" ]; then
    branch=$(git -C "$dir" branch --show-current 2>/dev/null)
    if [ -n "$branch" ]; then
        ref="🌿 $branch"
    else
        sha=$(git -C "$dir" rev-parse --short HEAD 2>/dev/null)
        [ -z "$sha" ] || ref="🔗 $sha"
    fi
fi

# THE PULL REQUEST the branch is in, before the folder (owner, 2026-09-18):
# 🔀 #386 for an open one, ✅ #386 once merged (the branch is done — go
# back to main), 🔀 N/A for a branch with no pull request, and nothing
# on a detached HEAD or outside a repository (no branch, no question).
# gh is asked at most once per TTL per (working copy, branch) — the
# status line redraws on every turn and a network call each time would
# be felt and rate-limited — through a small cache under XDG_CACHE_HOME;
# a gh that is missing or fails reads as "?" (unknown), never as N/A,
# because "no pull request" is a fact about GitHub and this line does
# not invent facts it could not read.
pr=""
if [ -n "$wc" ] && [ -n "${branch:-}" ]; then
    ttl="${AGENT_FABRIC_STATUSLINE_PR_TTL:-120}"
    cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/agent-fabric/statusline"
    key="$(printf '%s\n%s' "$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)" "$branch" | sha256sum | cut -c1-16)"
    cache="$cache_dir/pr-$key"
    fresh=""
    if [ -f "$cache" ]; then
        now=$(date +%s); mtime=$(stat -c %Y "$cache" 2>/dev/null || echo 0)
        [ $((now - mtime)) -lt "$ttl" ] && fresh="$(cat "$cache" 2>/dev/null)"
    fi
    if [ -z "$fresh" ]; then
        # The repository named as tools/fabric/gh.py's this_repo names it:
        # GH_REPO, else origin on github.com; never gh's default, which in a
        # fork clone is the upstream project (agent-fabric #109).
        repo="${GH_REPO:-$(git -C "$dir" remote get-url origin 2>/dev/null \
            | sed -nE 's#^([^@/:]+@github\.com:|(https|ssh|git)://([^@/]+@)?github\.com/)([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/?$#\4#p' \
            | sed -E 's#(\.git)?/?$##')}"
        if [ -n "$repo" ] && command -v gh >/dev/null 2>&1; then
            # The newest PR for this head branch, open first; state and number.
            found="$(cd "$dir" && gh pr list --repo "$repo" --head "$branch" --state all --limit 5 --json number,state 2>/dev/null \
                | jq -r 'sort_by(if .state == "OPEN" then 0 else 1 end) | .[0] | if . == null then "none" else "\(.state) \(.number)" end' 2>/dev/null)"
            [ -n "$found" ] || found="unknown"
        else
            found="unknown"
        fi
        fresh="$found"
        # An unknown is not cached: the next redraw asks again.
        if [ "$fresh" != "unknown" ]; then
            mkdir -p "$cache_dir" 2>/dev/null && printf '%s' "$fresh" > "$cache" 2>/dev/null
        fi
    fi
    case "$fresh" in
        OPEN\ *)   pr="🔀 #${fresh#OPEN }" ;;
        MERGED\ *) pr="✅ #${fresh#MERGED }" ;;
        CLOSED\ *) pr="🚫 #${fresh#CLOSED }" ;;
        none)      pr="🔀 N/A" ;;
        *)         pr="🔀 #?" ;;
    esac
fi

printf '[%s] 👤 %s@%s' "$harness" "$agent" "$host"
[ -z "$pr" ] || printf ' %s' "$pr"
printf ' 📁 %s' "${wc:-$(basename "$dir")}"
[ -z "$ref" ] || printf ' %s' "$ref"
