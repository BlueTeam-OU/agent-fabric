#!/usr/bin/env bash
# tests/test_fabric-fresh.sh — bin/fabric-fresh: an agent ends its own
# session at the end of a job; the launcher starts a fresh one.
#
# A fake parent named `claude` (a script's process name is its file name)
# runs the command, and AGENT_FABRIC_FRESH_KILL records the stop instead
# of sending it, so the suite checks the target without stopping anything.
set -uo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CMD="$ROOT/bin/fabric-fresh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fails=0
ok() { echo "  ✓ $1"; }
bad() { echo "  ✗ $1" >&2; [[ -n "${2:-}" ]] && printf '      %s\n' "$2" >&2; fails=$((fails + 1)); }

mkdir -p "$T/bin" "$T/state" "$T/wc"
cat > "$T/bin/record-kill" <<EOF
#!/usr/bin/env bash
echo "\$*" > "$T/killed"
EOF
# A real process named claude-fake (a copied bash: a script's process name
# is its interpreter's), never "claude": this suite runs inside a session.
cp "$(command -v bash)" "$T/bin/claude-fake"
cat > "$T/bin/claude" <<EOF
#!/usr/bin/env bash
exec "$T/bin/claude-fake" -c 'echo \$\$ > "$T/claude.pid"; cd "$T/wc" && "$CMD" "\$@"' claude-fake "\$@"
EOF
chmod +x "$T/bin/record-kill" "$T/bin/claude"
git -C "$T/wc" init -q; echo a > "$T/wc/f"; git -C "$T/wc" add f
git -C "$T/wc" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q -m a
envs=(AGENT_FABRIC_STATE_DIR="$T/state" AGENT_FABRIC_FRESH_KILL="$T/bin/record-kill" AGENT_FABRIC_FRESH_COMM=claude-fake AGENT_FABRIC_LAUNCH_OPENING=1)

echo "fabric-fresh: --help names every refusal and prints no code"
out="$("$CMD" --help 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "not started by the launcher" <<<"$out" && grep -q "uncommitted changes" <<<"$out" \
  && grep -q "its own prompt or -p" <<<"$out" && grep -q "predates fabric-fresh" <<<"$out" \
  && grep -q "no claude process" <<<"$out" && grep -q -- "--job <id>" <<<"$out" && ! grep -qE "set -uo|^note=" <<<"$out" \
  && ok "the five refusals, and the header ends before the code" || bad "help (rc=$rc)" "$out"

echo "fabric-fresh: refused where nothing would bring a session back"
out="$(env -u AGENT_FABRIC_LAUNCH_PROFILE "${envs[@]}" "$T/bin/claude" 2>&1)"; rc=$?
[[ $rc -eq 2 ]] && grep -q "not started by the launcher" <<<"$out" && [[ ! -e "$T/killed" ]] && ok "not launched: exit 2, nothing stopped" || bad "unlaunched (rc=$rc)" "$out"

echo "fabric-fresh: refused where the launch carried its own prompt"
out="$(env AGENT_FABRIC_LAUNCH_PROFILE=p "${envs[@]}" AGENT_FABRIC_LAUNCH_OPENING=0 "$T/bin/claude" 2>&1)"; rc=$?
[[ $rc -eq 2 ]] && grep -q "launched with its own prompt" <<<"$out" && [[ ! -e "$T/killed" ]] && ok "own prompt: exit 2, nothing stopped" || bad "own prompt (rc=$rc)" "$out"

out="$(env -u AGENT_FABRIC_LAUNCH_OPENING AGENT_FABRIC_LAUNCH_PROFILE=p AGENT_FABRIC_STATE_DIR="$T/state" AGENT_FABRIC_FRESH_KILL="$T/bin/record-kill" AGENT_FABRIC_FRESH_COMM=claude-fake "$T/bin/claude" 2>&1)"; rc=$?
[[ $rc -eq 2 ]] && grep -q "launcher predates fabric-fresh" <<<"$out" && [[ ! -e "$T/killed" ]] && ok "a launcher older than fabric-fresh: exit 2, said as such" || bad "old launcher (rc=$rc)" "$out"

echo "fabric-fresh: a job with uncommitted changes is not done"
echo new > "$T/wc/untracked"
out="$(env AGENT_FABRIC_LAUNCH_PROFILE=p "${envs[@]}" "$T/bin/claude" 2>&1)"; rc=$?
[[ $rc -eq 3 && ! -e "$T/killed" ]] && ok "an untracked file counts: exit 3" || bad "untracked (rc=$rc)" "$out"
rm "$T/wc/untracked"
echo b >> "$T/wc/f"
out="$(env AGENT_FABRIC_LAUNCH_PROFILE=p "${envs[@]}" "$T/bin/claude" 2>&1)"; rc=$?
[[ $rc -eq 3 ]] && grep -q "uncommitted changes" <<<"$out" && [[ ! -e "$T/killed" && ! -e "$T/state/agents/$(id -un)/restart.json" ]] && ok "dirty tree: exit 3, no marker, nothing stopped" || bad "dirty tree (rc=$rc)" "$out"
out="$(env AGENT_FABRIC_LAUNCH_PROFILE=p "${envs[@]}" "$T/bin/claude" --force 2>&1)"; rc=$?
[[ $rc -eq 0 && -e "$T/killed" ]] && ok "…--force goes ahead" || bad "--force (rc=$rc)" "$out"
git -C "$T/wc" checkout -q -- f; rm -f "$T/killed" "$T/state/agents/$(id -un)/restart.json"

echo "fabric-fresh: the marker the launcher reads, and the stop of the session above"
out="$(env AGENT_FABRIC_LAUNCH_PROFILE=p "${envs[@]}" "$T/bin/claude" --note "PR  981 merged" 2>&1)"; rc=$?
m="$T/state/agents/$(id -un)/restart.json"
[[ $rc -eq 0 && -f "$m" ]] && ok "clean tree: exit 0, marker written" || bad "no marker (rc=$rc)" "$out"
python3 - "$m" <<'PY' && ok "…fresh, done, the note on one line, requested_at a date" || bad "marker content" "$(cat "$m" 2>/dev/null)"
import datetime, json, sys
m = json.load(open(sys.argv[1]))
assert m["fresh"] is True and m["status"] == "done" and m["note"] == "PR 981 merged", m
datetime.datetime.fromisoformat(m["requested_at"].replace("Z", "+00:00"))
PY
[[ "$(cat "$T/killed" 2>/dev/null)" == "-TERM $(cat "$T/claude.pid")" ]] && ok "…and SIGTERM goes to the claude process above it" || bad "wrong target" "killed: $(cat "$T/killed" 2>/dev/null) claude: $(cat "$T/claude.pid")"

echo "fabric-fresh: a stop that fails takes its marker back"
rm -f "$m"
out="$(env AGENT_FABRIC_LAUNCH_PROFILE=p "${envs[@]}" AGENT_FABRIC_FRESH_KILL=false "$T/bin/claude" 2>&1)"; rc=$?
[[ $rc -eq 1 && ! -e "$m" ]] && grep -q "could not stop" <<<"$out" && ok "exit 1, no marker left for the next plain exit" || bad "failed stop (rc=$rc)" "$out"
# An upgrade's marker written between ours and the failed stop is not ours to remove.
cat > "$T/bin/kill-then-upgrade" <<EOF
#!/usr/bin/env bash
echo '{"requested_at":"2099-01-01T00:00:00Z","piece":"fabric","status":"pending"}' > "$m"
exit 1
EOF
chmod +x "$T/bin/kill-then-upgrade"
out="$(env AGENT_FABRIC_LAUNCH_PROFILE=p "${envs[@]}" AGENT_FABRIC_FRESH_KILL="$T/bin/kill-then-upgrade" "$T/bin/claude" 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && grep -q '"piece":"fabric"' "$m" 2>/dev/null && ok "…and an upgrade marker written since is left alone" || bad "removed another writer's marker (rc=$rc)" "$(cat "$m" 2>/dev/null)"
rm -f "$m"

echo "fabric-fresh: --job names the job the next session is for"
rm -f "$T/killed"
out="$(env AGENT_FABRIC_LAUNCH_PROFILE=p "${envs[@]}" "$T/bin/claude" --job j9 2>&1)"; rc=$?
[[ $rc -eq 2 && ! -e "$m" && ! -e "$T/killed" ]] && grep -q "no job j9" <<<"$out" && ok "an unknown job: exit 2, no marker, nothing stopped" || bad "unknown job (rc=$rc)" "$out"
(cd "$T/wc" && AGENT_FABRIC_ROOT="$ROOT" AGENT_FABRIC_STATE_DIR="$T/state" "$ROOT/bin/fabric-jobs" add "the next one" >/dev/null)
out="$(env AGENT_FABRIC_LAUNCH_PROFILE=p "${envs[@]}" "$T/bin/claude" --job j1 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); assert m["fresh"] is True and m["job"] == "j1", m' "$m" \
  && grep -q "starts a fresh one for job j1" <<<"$out" && ok "a listed job: its id in the marker, and said" || bad "job marker (rc=$rc)" "$out $(cat "$m" 2>/dev/null)"
rm -f "$m" "$T/killed"

echo "fabric-fresh: no claude above it"
out="$(cd "$T/wc" && env AGENT_FABRIC_LAUNCH_PROFILE=p "${envs[@]}" "$CMD" 2>&1)"; rc=$?
[[ $rc -eq 2 ]] && grep -q "no claude-fake process" <<<"$out" && ok "exit 2, nothing stopped" || bad "no claude (rc=$rc)" "$out"

if (( fails )); then echo "test_fabric-fresh: $fails FAILED"; exit 1; fi
echo "test_fabric-fresh: all assertions passed"
