#!/usr/bin/env bash
# Claude Code PostModelSwitch hook: when the harness switched the model
# on its own — a safeguard flagged the last request and the session fell
# back to another model — tell the session, at once, what that means.
#
# The docs (code.claude.com/docs/en/hooks, model-config, read 2026-09-16):
# PreModelSwitch is NOT run for a switch the harness makes itself; only
# PostModelSwitch is, with source "auto", requested_model null, and the
# switch is sticky — the session continues on the fallback model until
# /model. A PostModelSwitch hook cannot block; what it prints reaches the
# model with the next request. That is the channel this hook uses.
#
# WHY. The flagged text is contagious: a finding that tripped this
# session's safeguards trips every session it is sent to, and a
# broadcast lands in all of them at once. So the session is told, before
# it writes anything else, that nothing from that exchange goes into a
# GZCoord message, a commit, a PR body or a memory: from now on it
# filters out of everything it sends anything that could be read as the
# flagged category (a cybersecurity issue, most often), naming where a
# finding is and what class of problem it is, never its content — and
# that it now runs on a tier it was not launched with. A marker under the login's home lets gzcoord-send repeat the
# reminder on stderr at the moment of sending, and bin/fabric-status say
# the session fell back. The marker is per session (harness pid,
# CLAUDE_PID) like the plan-hold marker, and swept the same way.
#
# Silent on every switch the session asked for itself (source command,
# picker, sdk) and on a resume (the model restored is the one it had).
# Exit 0 always; nothing on stdout unless there is context to add.
set -uo pipefail
command -v jq >/dev/null 2>&1 || exit 0
input="$(cat)" || exit 0
[[ -n "$input" ]] || exit 0

{ read -r event; read -r source; read -r from; read -r to; read -r sid; read -r transcript; } < <(printf '%s' "$input" | jq -r '.hook_event_name // "", .source // "", .from_model // "", .to_model // "", .session_id // "", .transcript_path // ""' 2>/dev/null)
[[ "${event:-}" == "PostModelSwitch" && "${source:-}" == "auto" ]] || exit 0

# The flagged category is not in the hook input; the transcript records
# the fallback as a model_refusal_fallback line with apiRefusalCategory
# (read back 2026-09-15: "cyber"). The last such line is this switch.
category=""
if [[ -n "${transcript:-}" && -r "$transcript" ]]; then
  category="$(grep -a '"model_refusal_fallback"' "$transcript" 2>/dev/null | tail -1 | jq -r '.apiRefusalCategory // empty' 2>/dev/null)"
fi
case "${category:-}" in
  cyber*) topic="a cybersecurity issue" ;;
  bio*) topic="a biology or biosecurity issue" ;;
  "") topic="the category the safeguard flagged" ;;
  *) topic="a $category issue" ;;
esac

uid="$(id -u)"
dir="${AGENT_FABRIC_FALLBACK_DIR:-$HOME/.cache/agent-fabric/fallback}"
pid="${CLAUDE_PID:-$PPID}"
[[ "$pid" =~ ^[1-9][0-9]*$ ]] || pid=0
session="${CLAUDE_CODE_SESSION_ID:-${sid:-}}"
at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# The marker: ours, 700, not a symlink — or no marker, and the note alone.
if (( pid > 0 )); then
  mkdir -p -m 700 "$dir" 2>/dev/null
  if [[ ! -L "$dir" && -d "$dir" ]] && read -r owner perm < <(stat -c '%u %a' "$dir" 2>/dev/null) && [[ "$owner" == "$uid" ]]; then
    [[ "$perm" == "700" ]] || chmod 700 "$dir" 2>/dev/null
    for f in "$dir"/*.json; do
      [[ -f "$f" ]] || continue
      p="$(jq -r '.pid // 0' "$f" 2>/dev/null)"
      [[ "$p" =~ ^[1-9][0-9]*$ ]] && kill -0 "$p" 2>/dev/null || rm -f "$f" 2>/dev/null
    done
    tmp="$(mktemp "$dir/.$pid.XXXXXX" 2>/dev/null)" && \
      jq -n --arg s "$session" --argjson p "$pid" --arg f "$from" --arg t "$to" --arg at "$at" --arg c "${category:-}" --arg topic "$topic" \
         '{session_id: $s, pid: $p, from_model: $f, to_model: $t, at: $at, category: $c, topic: $topic}' > "$tmp" 2>/dev/null && \
      mv -f "$tmp" "$dir/$pid.json" 2>/dev/null
    rm -f "$tmp" 2>/dev/null
  fi
fi

note="agent-fabric: a safeguard flagged your last request as $topic and the harness switched this session from ${from:-the launched model} to ${to:-a fallback model} at $at; it stays there until /model. What flagged you flags every session it reaches, and a broadcast reaches all of them at once. From now on, filter out of everything you send — GZCoord messages, commit messages, PR bodies, memories — anything that could be read as $topic: name where such a finding is (file, line, PR) and what class of problem it is, never its content, and let the reader open it in their own repository. Say in your next report that this session fell back, and to what."
jq -n --arg n "$note" '{hookSpecificOutput: {hookEventName: "PostModelSwitch", additionalContext: $n}}'
exit 0
