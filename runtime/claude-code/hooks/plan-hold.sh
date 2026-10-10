#!/usr/bin/env bash
# Claude Code hook (PreToolUse on every tool, UserPromptSubmit, SessionEnd):
# hold this account's GZCoord inbox while a session is planning.
#
# A plan is written from the context the session has when it enters plan
# mode; a delivery landing in the middle of it is new context the plan
# was not asked to absorb. The harness gives no way to pause
# notifications, but the whole delivery path is ours: a message becomes a
# notification only because the watch (gzcoord-inbox --follow, in
# tools/fabric/gzcoord/inbox.py) polls the relay and prints it. So the session says
# "planning" through a marker, and the watch does not poll while a
# marker is live: nothing is consumed, the relay keeps the cursor, and
# the first poll after the plan is approved delivers everything at once.
#
# One marker per SESSION: $HOME/.cache/agent-fabric/hold/<pid>.json,
# naming the harness pid (CLAUDE_PID, exported to hooks; the hook's
# parent IS that process, verified on 2.1.273), its start time from
# /proc, and the session id. The account is held while ANY marker names
# a live harness of this login — two sessions planning under one login
# hold together and release separately (the first review found a single
# file per login released the sibling's hold). Under $HOME, not /tmp:
# another login could pre-create a per-uid name under /tmp and own the
# directory, and then hold or release this login's inbox (the same
# review, P1); the home is the login's. The directory must be ours, mode
# 700 and not a symlink, or the hook writes nothing.
#
# Every hook event carries permission_mode (verified live 2.1.273:
# UserPromptSubmit and PreToolUse; SessionStart does not), so the marker
# follows the mode rather than the EnterPlanMode/ExitPlanMode calls — a
# rejected plan stays in plan mode, and a plan entered by launch flag
# never calls EnterPlanMode. A subagent's event (agent_id present) is not
# the session's mode and is ignored. SessionEnd clears the session's own
# marker; every event sweeps markers whose harness is gone (dead pid, or
# a pid reused by a process with another start time).
#
# Exit 0 always, nothing on stdout: a hook that cannot run must not turn
# a planning session into a broken one. Without jq the marker is never
# written and the inbox behaves as before this hook existed.
set -uo pipefail
command -v jq >/dev/null 2>&1 || exit 0
input="$(cat)" || exit 0
[[ -n "$input" ]] || exit 0

uid="$(id -u)"
dir="${AGENT_FABRIC_HOLD_DIR:-$HOME/.cache/agent-fabric/hold}"
pid="${CLAUDE_PID:-$PPID}"
session="${CLAUDE_CODE_SESSION_ID:-}"

# One field per line: an empty field must stay empty (the harness sends
# agent_id: null for the session itself; a whitespace-split read would
# slide session_id into it and take the session for a subagent).
{ read -r event; read -r mode; read -r agent_id; read -r sid; } < <(printf '%s' "$input" | jq -r '.hook_event_name // "", .permission_mode // "", .agent_id // "", .session_id // ""' 2>/dev/null)
[[ -n "${event:-}" ]] || exit 0
[[ -z "${agent_id:-}" ]] || exit 0          # a subagent's mode is not the session's
[[ -n "$session" ]] || session="${sid:-}"
[[ "$pid" =~ ^[1-9][0-9]*$ ]] || exit 0

# The start time of a pid (clock ticks since boot; /proc/<pid>/stat field
# 22, read after the ')' that ends the command name). Empty off Linux.
start_of() { [[ -r "/proc/$1/stat" ]] && sed 's/.*) //' "/proc/$1/stat" 2>/dev/null | awk '{print $20}'; }
# Live: a positive pid (0 would signal the hook's own process group and
# succeed) that answers kill -0 as THIS login (EPERM is another login's
# process, never our harness) and, when both sides know it, was started
# when the marker says.
alive() {
  local p="$1" s="$2" now
  [[ "$p" =~ ^[1-9][0-9]*$ ]] || return 1
  kill -0 "$p" 2>/dev/null || return 1
  now="$(start_of "$p")"
  [[ -z "$s" || -z "$now" || "$s" == "$now" ]]
}

# The directory: ours, 700, not a symlink — or nothing is written or read.
mkdir -p -m 700 "$dir" 2>/dev/null
[[ ! -L "$dir" && -d "$dir" ]] || exit 0
read -r owner perm < <(stat -c '%u %a' "$dir" 2>/dev/null) || exit 0
[[ "$owner" == "$uid" ]] || exit 0
[[ "$perm" == "700" ]] || chmod 700 "$dir" 2>/dev/null || exit 0

marker="$dir/$pid.json"

# Sweep: a marker whose harness is gone is nobody's hold.
for f in "$dir"/*.json; do
  [[ -f "$f" ]] || continue
  read -r p s < <(jq -r '[(.pid // 0 | tostring), (.start // "" | tostring)] | join(" ")' "$f" 2>/dev/null)
  [[ "$f" == "$marker" ]] && continue
  alive "${p:-}" "${s:-}" || rm -f "$f" 2>/dev/null
done

if [[ "$event" != "SessionEnd" && "$mode" == "plan" ]]; then
  # Held. Written once: a marker already naming this pid stays.
  [[ -f "$marker" ]] && exit 0
  tmp="$(mktemp "$dir/.$pid.XXXXXX" 2>/dev/null)" || exit 0
  jq -n --arg s "$session" --argjson p "$pid" --arg st "$(start_of "$pid")" --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     '{session_id: $s, pid: $p, start: $st, since: $t}' > "$tmp" 2>/dev/null && mv -f "$tmp" "$marker" 2>/dev/null
  rm -f "$tmp" 2>/dev/null
  exit 0
fi

# Not planning, or ending: this session's own marker goes. Another live
# session's marker is its own.
rm -f "$marker" 2>/dev/null
exit 0
