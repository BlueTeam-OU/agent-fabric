#!/usr/bin/env bash
# Behavioural tests for runtime/claude-code/hooks/plan-hold.sh: the marker
# that holds this account's GZCoord inbox while the session plans.
#
# What this holds still: a marker per session appears on a plan-mode
# event and only then; it names the session's harness pid and start
# time; it is written once per session; a subagent's event never touches
# it; a non-plan event clears the session's own marker and any marker
# whose harness is gone, never another live session's — two sessions
# planning under one login hold and release independently; SessionEnd
# clears; the hold directory must be the login's own, 700, not a symlink;
# the hook is silent and exits 0 on every input, malformed included. The
# reader side (gzcoord-inbox --held, and the watch not polling) is in
# communication/gzcoord/tests.
#
# Exit 0 all passed, 1 otherwise.
set -uo pipefail
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/plan-hold.sh"
[[ -f "$UNDER_TEST" ]] || { echo "test: not found: $UNDER_TEST" >&2; exit 1; }
command -v jq >/dev/null || { echo "test: jq required" >&2; exit 1; }

failures=0
pass() { echo "  ok   $1"; }
fail() { echo "  FAIL $1" >&2; [[ $# -gt 1 ]] && printf '       %s\n' "$2" >&2; failures=$((failures + 1)); }
SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT
export AGENT_FABRIC_HOLD_DIR="$SANDBOX/hold"
MARKER="$AGENT_FABRIC_HOLD_DIR/$$.json"

# fire <event> <mode|-> <agent_id|-> [pid] [session] -> stdout of the hook (must be empty)
fire() {
  local event="$1" mode="$2" agent="$3" pid="${4:-$$}" session="${5:-sess-1}" payload
  # The shape the harness sends (2.1.273): session_id present, agent_id
  # null for the session itself — an empty field in the middle.
  payload="$(jq -nc --arg e "$event" --arg m "$mode" --arg a "$agent" --arg s "$session" '{hook_event_name:$e, session_id:$s, agent_id:null, transcript_path:"/t", cwd:"/"} + (if $m != "-" then {permission_mode:$m} else {} end) + (if $a != "-" then {agent_id:$a, agent_type:"code-low"} else {} end)')"
  printf '%s' "$payload" | CLAUDE_PID="$pid" CLAUDE_CODE_SESSION_ID="$session" bash "$UNDER_TEST"
  echo "rc=$?"
}
expect_out() { local label="$1" got="$2"; if [[ "$got" == "rc=0" ]]; then pass "$label"; else fail "$label" "hook printed or failed: $got"; fi; }
expect_marker() { local label="$1" want="$2"; if [[ -f "$MARKER" ]]; then got=present; else got=absent; fi; if [[ "$got" == "$want" ]]; then pass "$label"; else fail "$label" "want marker $want, got $got"; fi; }

echo "plan hold: the marker follows the permission mode"
expect_out "a default-mode tool call is silent" "$(fire PreToolUse default -)"
expect_marker "no marker outside plan mode" absent
expect_out "a plan-mode tool call is silent" "$(fire PreToolUse plan -)"
expect_marker "the marker appears on a plan-mode event" present
start_now="$(sed 's/.*) //' /proc/$$/stat | awk '{print $20}')"
if [[ "$(jq -r .pid "$MARKER")" == "$$" && "$(jq -r .session_id "$MARKER")" == "sess-1" && "$(jq -r .start "$MARKER")" == "$start_now" ]]; then pass "the marker names the harness pid, its start time and the session"; else fail "the marker names the harness pid, its start time and the session" "$(cat "$MARKER")"; fi
if [[ "$(stat -c %a "$AGENT_FABRIC_HOLD_DIR")" == "700" ]]; then pass "the hold directory is 700"; else fail "the hold directory is 700"; fi
first="$(stat -c %Y "$MARKER" 2>/dev/null || stat -f %m "$MARKER")"; sleep 1.1
fire UserPromptSubmit plan - >/dev/null
second="$(stat -c %Y "$MARKER" 2>/dev/null || stat -f %m "$MARKER")"
if [[ "$first" == "$second" ]]; then pass "a marker naming this pid is written once, not per event"; else fail "a marker naming this pid is written once, not per event"; fi

echo "plan hold: leaving plan mode clears it"
expect_out "a default-mode prompt is silent" "$(fire UserPromptSubmit default -)"
expect_marker "the marker is gone after a non-plan event of the same session" absent

echo "plan hold: a subagent's event is not the session's mode"
fire PreToolUse plan sub-1 >/dev/null
expect_marker "a plan-mode event with agent_id writes nothing" absent
fire PreToolUse plan - >/dev/null
fire PreToolUse default sub-1 >/dev/null
expect_marker "a default-mode event with agent_id clears nothing" present

echo "plan hold: two sessions under one login hold and release independently"
# a second live harness of this login: a sleeping child of the test
sleep 300 & OTHER=$!
fire PreToolUse plan - "$OTHER" sess-2 >/dev/null
OTHER_MARKER="$AGENT_FABRIC_HOLD_DIR/$OTHER.json"
if [[ -f "$MARKER" && -f "$OTHER_MARKER" ]]; then pass "each planning session has its own marker"; else fail "each planning session has its own marker" "$(ls "$AGENT_FABRIC_HOLD_DIR")"; fi
fire UserPromptSubmit default - "$OTHER" sess-2 >/dev/null   # the second session's plan is approved first
expect_marker "the first session is still held after the second released" present
if [[ ! -f "$OTHER_MARKER" ]]; then pass "the second session's marker is gone"; else fail "the second session's marker is gone"; fi
fire PreToolUse plan - "$OTHER" sess-2 >/dev/null
fire UserPromptSubmit default - >/dev/null                     # now the first releases
if [[ ! -f "$MARKER" && -f "$OTHER_MARKER" ]]; then pass "the second session stays held after the first released"; else fail "the second session stays held after the first released"; fi
fire PreToolUse plan - >/dev/null

echo "plan hold: a marker whose harness is gone is swept by any event"
kill "$OTHER" 2>/dev/null; wait "$OTHER" 2>/dev/null
fire PreToolUse plan - >/dev/null
if [[ ! -f "$OTHER_MARKER" ]]; then pass "a dead session's marker is swept"; else fail "a dead session's marker is swept"; fi
expect_marker "our own is kept" present
# a live pid with another start time is a reused pid, not the harness
sleep 300 & OTHER=$!; OTHER_MARKER="$AGENT_FABRIC_HOLD_DIR/$OTHER.json"
fire PreToolUse plan - "$OTHER" sess-3 >/dev/null
jq '.start = "1"' "$OTHER_MARKER" > "$OTHER_MARKER.tmp" && mv "$OTHER_MARKER.tmp" "$OTHER_MARKER"
fire PreToolUse plan - >/dev/null
if [[ ! -f "$OTHER_MARKER" ]]; then pass "a marker whose pid was reused is swept"; else fail "a marker whose pid was reused is swept"; fi
kill "$OTHER" 2>/dev/null; wait "$OTHER" 2>/dev/null
# pid 1 answers kill -0 with EPERM as an unprivileged login: not our harness
printf '{"pid":1,"session_id":"forged","start":""}\n' > "$AGENT_FABRIC_HOLD_DIR/1.json"
fire PreToolUse plan - >/dev/null
if [[ ! -f "$AGENT_FABRIC_HOLD_DIR/1.json" ]]; then pass "a marker naming another login's process is swept"; else fail "a marker naming another login's process is swept"; fi
# pid 0 would signal the hook's own process group and succeed: a marker naming no harness is swept
printf '{"session_id":"nopid"}\n' > "$AGENT_FABRIC_HOLD_DIR/7.json"; printf '{"pid":0}\n' > "$AGENT_FABRIC_HOLD_DIR/8.json"
fire PreToolUse plan - >/dev/null
if [[ ! -f "$AGENT_FABRIC_HOLD_DIR/7.json" && ! -f "$AGENT_FABRIC_HOLD_DIR/8.json" ]]; then pass "a marker naming no pid, or pid 0, is swept"; else fail "a marker naming no pid, or pid 0, is swept" "$(ls "$AGENT_FABRIC_HOLD_DIR")"; fi

echo "plan hold: the directory must be the login's own"
fire UserPromptSubmit default - >/dev/null
rm -rf "$AGENT_FABRIC_HOLD_DIR"; mkdir -p "$SANDBOX/elsewhere"; ln -s "$SANDBOX/elsewhere" "$AGENT_FABRIC_HOLD_DIR"
fire PreToolUse plan - >/dev/null
if [[ -z "$(ls -A "$SANDBOX/elsewhere")" ]]; then pass "a symlinked hold directory gets nothing"; else fail "a symlinked hold directory gets nothing"; fi
rm -f "$AGENT_FABRIC_HOLD_DIR"; mkdir -m 755 "$AGENT_FABRIC_HOLD_DIR"
fire PreToolUse plan - >/dev/null
if [[ "$(stat -c %a "$AGENT_FABRIC_HOLD_DIR")" == "700" && -f "$MARKER" ]]; then pass "our own directory with a loose mode is tightened and used"; else fail "our own directory with a loose mode is tightened and used"; fi

echo "plan hold: SessionEnd clears the session's own marker"
fire PreToolUse plan - >/dev/null
expect_marker "held" present
expect_out "SessionEnd is silent" "$(fire SessionEnd - -)"
expect_marker "cleared at session end" absent

echo "plan hold: never loud"
out="$(printf 'not json' | bash "$UNDER_TEST"; echo "rc=$?")"; expect_out "malformed input is silent" "$out"
out="$(printf '' | bash "$UNDER_TEST"; echo "rc=$?")"; expect_out "empty input is silent" "$out"
out="$(printf '{}' | bash "$UNDER_TEST"; echo "rc=$?")"; expect_out "an event without a name is silent" "$out"
expect_marker "and writes nothing" absent

if (( failures )); then echo "plan hold: $failures failure(s)" >&2; exit 1; fi
echo "plan hold: OK — all assertions passed."
