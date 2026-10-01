#!/usr/bin/env bash
# runtime/claude-code/test_user-settings.sh
#
# The fabric's keys in a login's user settings: user-settings.py writes
# attribution {commit "", pr "", sessionUrl false}, showThinkingSummaries
# true and verbose true, keeps every other key, replaces the deprecated
# includeCoAuthoredBy, is idempotent, refuses a flag instead of writing it
# as a path, and bootstrap.sh runs it.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ✓ %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  ✗ %s\n' "$1"; [[ -n "${2:-}" ]] && printf '%s\n' "$2" | sed 's/^/      /' | head -6; }
SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT
S="$SANDBOX/.claude/settings.json"
# The links bootstrap makes: a rule is granted only where the link is the
# fabric's script.
FABRIC="$(cd "$HERE/../.." && pwd)"
# Inside .claude/: the flag cases assert nothing else appears in the sandbox.
export AGENT_FABRIC_LOCAL_BIN="$SANDBOX/.claude/local-bin"; mkdir -p "$AGENT_FABRIC_LOCAL_BIN"
while IFS=$'\t' read -r name rel; do ln -s "$FABRIC/$rel" "$AGENT_FABRIC_LOCAL_BIN/$name"; done \
    < <(python3 -c 'import json,sys; [print(f"{k}\t{v}") for k, v in json.load(open(sys.argv[1]))["commands"].items()]' "$HERE/commands.json")
# Claude Code's auto-mode defaults from a stand-in (inside .claude/, as
# above): a runner without claude would otherwise make every write say the
# defaults could not be read. tests/test_user_settings_auto_mode.py tests
# autoMode itself.
printf '%s\n' '#!/bin/sh' 'echo '"'"'{"environment": ["**Organization**: None configured"], "allow": [], "soft_deny": [], "hard_deny": []}'"'" \
    > "$SANDBOX/.claude/claude"; chmod +x "$SANDBOX/.claude/claude"
export AGENT_FABRIC_CLAUDE="$SANDBOX/.claude/claude"
run() { python3 "$HERE/user-settings.py" "$@" 2>&1; }
check() { python3 -c "import json,sys; d=json.load(open('$S')); a=d['attribution']; assert (a['commit'],a['pr'],a['sessionUrl'])==('','',False), d; assert d['showThinkingSummaries'] is True and d['verbose'] is True and d['tui'] == 'default', d; assert d['env']['DISABLE_AUTOUPDATER'] == '1', d; $1" 2>&1; }

echo "a login with no settings file"
out="$(run "$S" --dry-run)"; [[ "$out" == "  +  $S fabric user settings (would write)" && ! -e "$S" ]] && ok "dry run names it and writes nothing" || bad "dry run" "$out"
out="$(run "$S")"; [[ "$out" == "  +  $S fabric user settings" ]] && check "" >/dev/null && ok "written, the directory created, every key present" || bad "write" "$out $(cat "$S" 2>&1)"
out="$(run "$S")"; [[ "$out" == "  =  $S fabric user settings" ]] && ok "a second run changes nothing" || bad "idempotence" "$out"

echo "a login with settings of its own"
printf '{"theme": "dark", "includeCoAuthoredBy": false, "attribution": {"commit": "Co-Authored-By: x", "extra": 1}, "permissions": {"deny": ["WebSearch"]}, "env": {"KEEP_ME": "yes"}}\n' > "$S"
out="$(run "$S")"
[[ "$out" == "  +  "* ]] && msg="$(check "assert d['theme']=='dark' and d['permissions']['deny']==['WebSearch'] and d['attribution']['extra']==1 and 'includeCoAuthoredBy' not in d and d['env']['KEEP_ME']=='yes', d")" && ok "the keys set, the deprecated switch removed, everything else kept" || bad "merge" "$out ${msg:-} $(cat "$S")"
printf '{"attribution": {"commit": "", "pr": "", "sessionUrl": false}, "includeCoAuthoredBy": true, "showThinkingSummaries": true, "verbose": true}\n' > "$S"
out="$(run "$S")"; [[ "$out" == "  +  "* ]] && check "assert 'includeCoAuthoredBy' not in d" >/dev/null && ok "a deprecated switch beside the keys is still removed" || bad "deprecated switch" "$out"
# The display keys are what an account bootstrapped before 2026-09-20
# lacks: attribution already off, nothing else set. That account is
# rewritten, not reported settled.
printf '{"attribution": {"commit": "", "pr": "", "sessionUrl": false}, "verbose": false}\n' > "$S"
out="$(run "$S")"; [[ "$out" == "  +  "* ]] && check "" >/dev/null && ok "attribution already off, the display keys still written (verbose false overridden)" || bad "display keys" "$out $(cat "$S")"
# What every account had before DISABLE_AUTOUPDATER was a fabric key:
# attribution off, the display keys set, no env. Rewritten, not settled.
printf '{"attribution": {"commit": "", "pr": "", "sessionUrl": false}, "showThinkingSummaries": true, "verbose": true}\n' > "$S"
out="$(run "$S")"; [[ "$out" == "  +  "* ]] && check "" >/dev/null && ok "a settings file from before the auto-update key gets it (not reported settled)" || bad "auto-update key not written" "$out $(cat "$S")"
printf 'not json\n' > "$S"; out="$(run "$S" 2>&1)"; rc=$?
[[ $rc -eq 1 && "$out" == "  !  "*"NOT written"* && "$(cat "$S")" == "not json" ]] && ok "an unreadable file is refused with one line, not a traceback, and not overwritten" || bad "unreadable file" "$out"
printf '[1]\n' > "$S"; out="$(run "$S" 2>&1)"; rc=$?
[[ $rc -eq 1 && "$(cat "$S")" == "[1]" ]] && ok "a JSON file that is not an object is refused too" || bad "non-object" "$out"
out="$(run 2>&1)"; [[ $? -eq 2 ]] && ok "no path: usage, exit 2" || bad "usage" "$out"

echo "the memory-write check at user scope"
printf '{"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}, {"matcher": "Write|Edit", "hooks": [{"type": "command", "command": "python3 \\"/old/place/runtime/claude-code/hooks/memory-write-check.py\\""}]}], "Stop": [{"hooks": [{"type": "command", "command": "stop.sh"}]}]}}\n' > "$S"
out="$(run "$S")"
msg="$(check "p=d['hooks']['PostToolUse']; mc=[e for e in p if 'memory-write-check.py' in e['hooks'][0]['command']]; assert len(mc)==1 and mc[0]['matcher']=='Write|Edit' and '$FABRIC/runtime/claude-code/hooks/memory-write-check.py' in mc[0]['hooks'][0]['command'], p; assert any(e['hooks'][0]['command']=='mine.sh' for e in p) and d['hooks']['Stop'][0]['hooks'][0]['command']=='stop.sh', d")" \
  && ok "one entry, at this checkout's path (an old path replaced); the account's own hooks kept" || bad "memory check hook" "$out ${msg:-} $(cat "$S")"
out="$(run "$S")"; [[ "$out" == "  =  $S fabric user settings" ]] && ok "…and a second run changes nothing" || bad "hook idempotence" "$out"
# A hand-merged entry holding the check beside a hook of the account's own:
# only the check is replaced; the neighbour stays.
printf '{"hooks": {"PostToolUse": [{"matcher": "Write|Edit", "hooks": [{"type": "command", "command": "python3 \\"/old/runtime/claude-code/hooks/memory-write-check.py\\""}, {"type": "command", "command": "neighbour.sh"}]}]}}\n' > "$S"
out="$(run "$S")"
msg="$(check "p=d['hooks']['PostToolUse']; cmds=[h['command'] for e in p for h in e['hooks']]; assert 'neighbour.sh' in cmds, p; assert sum('memory-write-check.py' in c for c in cmds)==1 and not any('/old/' in c for c in cmds), p")" \
  && ok "a hook sharing the check's entry is kept" || bad "neighbour hook" "$out ${msg:-} $(cat "$S")"
# PostToolUse that is not a list is the account's own mistake: left exactly
# as it is and said, never iterated into junk entries; not reported settled.
for bad_shape in '{"matcher": "x", "hooks": []}' '"ab"'; do
    # Every other key unset too, so settled() is false before it reaches
    # the hooks: the refusal must come from the check itself, not by luck.
    printf '{"hooks": {"PostToolUse": %s}}\n' "$bad_shape" > "$S"
    for mode in "" --dry-run; do
        out="$(run "$S" $mode 2>&1)"; rc=$?
        msg="$(python3 -c "import json,sys; d=json.load(open('$S')); assert d['hooks']['PostToolUse']==json.loads(sys.argv[1]), d" "$bad_shape" 2>&1)" \
          && [[ $rc -eq 1 && "$out" == "  !  "*"PostToolUse is not a list"*"NOT written" && "$(printf '%s\n' "$out" | wc -l)" -eq 1 && "$out" != *Traceback* ]] \
          && ok "a PostToolUse of shape $bad_shape is refused in one line, untouched${mode:+ ($mode)}" || bad "malformed PostToolUse $bad_shape ${mode}" "rc=$rc $out ${msg:-} $(cat "$S")"
    done
done
# An entry that is not an object inside a well-formed list is kept as it is.
printf '{"hooks": {"PostToolUse": ["odd", {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}]}}\n' > "$S"
out="$(run "$S")"
msg="$(check "p=d['hooks']['PostToolUse']; assert p[0]=='odd' and any(e!='odd' and e['hooks'][0]['command']=='mine.sh' for e in p) and sum(1 for e in p if isinstance(e,dict) and 'memory-write-check.py' in e['hooks'][0]['command'])==1, p")" \
  && ok "an unparseable entry in the list is kept as it is" || bad "odd entry" "$out ${msg:-} $(cat "$S")"

echo "bootstrap runs it"
grep -q 'user-settings.py" "\$CLAUDE_HOME/settings.json"' "$HERE/bootstrap.sh" && ok "bootstrap.sh calls it on the login's user settings" || bad "bootstrap wiring"
grep -q 'attribution-off' "$HERE/bootstrap.sh" && bad "bootstrap.sh still names the retired writer" || ok "the retired name is gone from bootstrap.sh"
grep -q 'failed=\$((failed+1))' "$HERE/bootstrap.sh" && ok "a refused write is counted, not read as already current" || bad "bootstrap accounting"

echo "a flag is never a path"
cd "$SANDBOX" || exit 1
for flag in --help -h; do
    out="$(python3 "$HERE/user-settings.py" "$flag" 2>/dev/null)"; rc=$?
    [[ $rc -eq 0 && "$out" == *"user-settings.py <settings.json> [--dry-run]"* && -z "$(ls -A "$SANDBOX" | grep -v '^\.claude$')" ]] \
        && ok "$flag prints the usage on stdout and writes nothing" || bad "$flag" "rc=$rc $out $(ls -A "$SANDBOX")"
done
for flag in --verbose -x -; do
    err="$(python3 "$HERE/user-settings.py" "$flag" 2>&1 1>/dev/null)"; rc=$?
    [[ $rc -eq 2 && ! -e "$SANDBOX/$flag" && "$err" == *"$flag: not an option and not a path"* ]] \
        && ok "$flag is refused by name on stderr, not written as a file" || bad "unknown flag $flag" "rc=$rc $err"
done
out="$(run --dry-run --bogus)"; rc=$?
[[ $rc -eq 2 && ! -e "$SANDBOX/--bogus" ]] && ok "…beside --dry-run too" || bad "unknown flag with --dry-run" "rc=$rc $out"
out="$(python3 -OO "$HERE/user-settings.py" --help 2>&1)"; rc=$?
[[ $rc -eq 0 && "$out" == *"<settings.json>"* ]] && ok "the usage survives python3 -OO" || bad "-OO" "rc=$rc $out"
# The fabric's commands are allowed by a narrow rule each; the account's
# own allow, deny and ask rules stay as they were, and a wrapper that runs
# another command is never allowed (the owner, 2026-09-26).
mkdir -p "$(dirname "$S")"
printf '%s\n' '{"permissions":{"allow":["Bash(ls *)"],"ask":["Bash(gzcoord-send *)"],"deny":["Bash(rm *)"]}}' > "$S"
run "$S" >/dev/null
perm="$(jq -c .permissions "$S")"
jq -e '.allow | index("Bash(ls *)") and index("Bash(gzcoord-inbox *)") and index("Bash(fabric-status *)")' <<<"$perm" >/dev/null \
    && ok "each fabric command gets a narrow allow rule, beside the account's own" || bad "allow rules" "$perm"
jq -e '.ask == ["Bash(gzcoord-send *)"] and .deny == ["Bash(rm *)"]' <<<"$perm" >/dev/null \
    && ok "…the account's ask and deny rules are untouched (an ask still wins)" || bad "ask/deny changed" "$perm"
jq -e '[.allow[] | select(. == "Bash(fabric-lease *)" or . == "Bash(fabric-host *)")] | length == 0' <<<"$perm" >/dev/null \
    && ok "…and fabric-lease and fabric-host, which run other commands, get none" || bad "wrapper allowed" "$perm"
out="$(run "$S")"; [[ "$out" == "  =  "* ]] && ok "…and a second run changes nothing" || bad "not idempotent" "$out"
# An account the earlier bootstrap already settled — every other key in
# place, no allow rule yet — still gets the rules: a check that ignored
# them would print "=" and never write them (review of #42).
jq 'del(.permissions.allow)' "$S" > "$S.tmp" && mv "$S.tmp" "$S"
out="$(run "$S")"
[[ "$out" == "  +  "* ]] && jq -e '.permissions.allow | index("Bash(gzcoord-inbox *)")' "$S" >/dev/null \
    && ok "a settings file settled but for the allow rules gets them" || bad "settled file left without rules" "$out"
# A foreign file at a command's name (bootstrap refused to replace it) gets
# no rule, and a rule granted before is withdrawn: the name would run that
# file under the fabric's approval (review of #42).
rm -f "$AGENT_FABRIC_LOCAL_BIN/gzmsg"; printf '#!/bin/sh\necho mine\n' > "$AGENT_FABRIC_LOCAL_BIN/gzmsg"
out="$(run "$S")"
jq -e '(.permissions.allow | index("Bash(gzmsg *)")) == null and (.permissions.allow | index("Bash(gzcoord-send *)")) != null' "$S" >/dev/null \
    && ok "a name that is not the fabric's script gets no rule, and loses one it had" || bad "foreign name allowed" "$(jq -c .permissions.allow "$S")"
rm -f "$AGENT_FABRIC_LOCAL_BIN/gzmsg"; ln -s "$FABRIC/communication/gzcoord/scripts/gzmsg.mjs" "$AGENT_FABRIC_LOCAL_BIN/gzmsg"; run "$S" >/dev/null
# Every session starts in auto mode (the owner, 2026-09-26): a file
# settled in every other key but the mode is written.
jq 'del(.permissions.defaultMode)' "$S" > "$S.tmp" && mv "$S.tmp" "$S"
out="$(run "$S")"
[[ "$out" == "  +  "* && "$(jq -r .permissions.defaultMode "$S")" == auto ]] \
    && ok "a missing permission mode is set to auto" || bad "mode not set" "$out $(jq -c .permissions "$S")"
cd "$HERE" || exit 1

echo; echo "user-settings: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
