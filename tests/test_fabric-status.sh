#!/usr/bin/env bash
# tests/test_fabric-status.sh — bin/fabric-status says what this session was
# launched as, and says DRIFT when the binding, the session default or the
# prompt file moved under it. Runs the real script against a throwaway
# state dir; the stamps a launch exports are forged in the environment.
set -uo pipefail
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"; ROOT="$(dirname "$HERE")"
PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; [[ -n "${2:-}" ]] && echo "$2" | sed 's/^/      /'; }

SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT
STATE="$SANDBOX/state"; LOGIN="$(id -un)"
mkdir -p "$STATE/agents/$LOGIN"
printf '{"agent":"%s","host":"'"$(hostname -s)"'","role":"db-admin","updated_at":"x"}\n' "$LOGIN" > "$STATE/agents/$LOGIN/binding.json"
printf 'prompt text\n' > "$STATE/agents/$LOGIN/launch-prompt.md"
DIGEST="sha256:$(sha256sum "$STATE/agents/$LOGIN/launch-prompt.md" | cut -d' ' -f1)"

# Nothing a real session exported may leak into the forged one; and the
# login is placed on this host in a fixture registry (the real one need
# not know a CI runner's login) unless a case names another.
PLACED="$SANDBOX/placed.json"
printf '{"version":1,"hosts":{"%s":{"platform":"fedora-qubes","ssh":null,"operator":"%s","fabric":"x"}},"placement":{"%s":"%s"}}\n' "$(hostname -s)" "$LOGIN" "$LOGIN" "$(hostname -s)" > "$PLACED"
# CLAUDE_EFFORT is the RUNNING session's own read-back, not the fabric's:
# it is set in every real agent's environment and in none on CI, and it
# moves mid-session (measured 2026-09-23: high, then xhigh untouched). Left
# unscrubbed it reached the fixture and every case saw a spurious effort
# line — green on CI, red on every holder, the same shape as the locale
# leak this branch already fixed. A case that wants one sets it explicitly.
# CLAUDE_CODE_OAUTH_TOKEN and CLAUDE_CONFIG_DIR likewise: a login moved to
# an account template carries the first, and the sign-in line would differ.
# HOME too: fabric-status reads the login's synced record from it, and once
# every login ran on a template (2026-09-25) the record disagreed with the
# scrubbed environment and every holder saw a sign-in DRIFT CI never did.
mkdir -p "$SANDBOX/home"
status() { env -u AGENT_FABRIC_LAUNCH_ROLE -u AGENT_FABRIC_LAUNCH_PROMPT_DIGEST -u AGENT_FABRIC_LAUNCH_SESSION_MODEL \
               -u AGENT_FABRIC_LAUNCH_PROVIDER -u AGENT_FABRIC_LAUNCH_PROFILE -u ANTHROPIC_BASE_URL \
               -u CLAUDE_EFFORT -u AGENT_FABRIC_LAUNCH_EFFORT -u CLAUDE_CODE_OAUTH_TOKEN -u CLAUDE_CONFIG_DIR \
               HOME="$SANDBOX/home" AGENT_FABRIC_STATE_DIR="$STATE" AGENT_FABRIC_HOSTS_REGISTRY="$PLACED" "$@" bash "$ROOT/bin/fabric-status" "${MODE[@]}"; }
MODE=()

echo "fabric-status: unlaunched — nothing to drift from"
out="$(status 2>&1)"
grep -q "^role         db-admin" <<<"$out" && ok "the bound role" || bad "role missing" "$out"
! grep -q "DRIFT\|launched as" <<<"$out" && ok "no launch stamp: no drift line, no 'launched as'" || bad "drift without a stamp" "$out"

echo "fabric-status: launched as the bound role, prompt intact"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROMPT_DIGEST="$DIGEST" AGENT_FABRIC_LAUNCH_PROVIDER=anthropic 2>&1)"
grep -q "^launched as  db-admin    prompt $DIGEST" <<<"$out" && ok "says what it was launched as, with the prompt digest" || bad "no launched-as line" "$out"
! grep -q "DRIFT" <<<"$out" && ok "…and no drift" || bad "false drift" "$out"

echo "fabric-status: the binding moved under the session"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=backend-dev AGENT_FABRIC_LAUNCH_PROMPT_DIGEST="$DIGEST" 2>&1)"
grep -q "^DRIFT        launched as backend-dev, binding now db-admin" <<<"$out" && grep -q "relaunch to hold db-admin" <<<"$out" && ok "role drift is one DRIFT line naming both and the fix" || bad "role drift not said" "$out"
MODE=(--json); out="$(status AGENT_FABRIC_LAUNCH_ROLE=backend-dev 2>&1)"; MODE=()
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["launched_role"]=="backend-dev" and any("binding now db-admin" in x for x in d["drift"])' <<<"$out" && ok "…and in the JSON report" || bad "json report lacks drift" "$out"

echo "fabric-status: the prompt file moved under the session"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROMPT_DIGEST=sha256:0000 2>&1)"
grep -q "^DRIFT        the prompt file was rewritten since launch" <<<"$out" && ok "a digest mismatch is said" || bad "prompt drift not said" "$out"
rm "$STATE/agents/$LOGIN/launch-prompt.md"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROMPT_DIGEST="$DIGEST" 2>&1)"
grep -q "^DRIFT        the launched prompt file is gone" <<<"$out" && ok "a missing file is said, not a crash" || bad "missing prompt file" "$out"

echo "fabric-status: the session default moved under the session"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROVIDER=anthropic AGENT_FABRIC_LAUNCH_SESSION_MODEL=claude-sonnet-5 2>&1)"
grep -q "^DRIFT        launched on claude-sonnet-5, the anthropic session now resolves to" <<<"$out" && grep -q "relaunch to apply" <<<"$out" && ok "a changed session default is said with the current resolution" || bad "session drift not said" "$out"
current="$(grep "the anthropic session now resolves to" <<<"$out" | sed 's/.*resolves to \([^ ]*\) .*/\1/')"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROVIDER=anthropic AGENT_FABRIC_LAUNCH_SESSION_MODEL="$current" 2>&1)"
! grep -q "launched on" <<<"$out" && ok "launched on what now resolves: no drift" || bad "false session drift" "$out"

echo "fabric-status: effort — the intent is shown, the drift waits for a stamp"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROVIDER=anthropic CLAUDE_EFFORT=xhigh 2>&1)"
grep -q "^session effort .* (asked; not pinned at launch) (running xhigh)" <<<"$out" && ok "unpinned: the asked-for level and the running one, side by side" || bad "effort intent not shown" "$out"
! grep -q "DRIFT.*effort" <<<"$out" && ok "…and no DRIFT: nothing pinned it, so nothing drifted from it" || bad "drift without an effort stamp" "$out"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROVIDER=anthropic AGENT_FABRIC_LAUNCH_EFFORT=max CLAUDE_EFFORT=high 2>&1)"
grep -q "^DRIFT        launched at effort max, the session is running at high" <<<"$out" && ok "pinned and clamped: one DRIFT line naming both levels" || bad "effort drift not said" "$out"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROVIDER=anthropic AGENT_FABRIC_LAUNCH_EFFORT=high CLAUDE_EFFORT=high 2>&1)"
! grep -q "DRIFT.*effort" <<<"$out" && grep -q "(confirmed)" <<<"$out" && ok "pinned and honoured: confirmed, no drift" || bad "false effort drift" "$out"
# The STAMP is the headline once there is one: it is what this session was
# started with. The resolved intent only says what a relaunch would do, and
# printing it first described a different session.
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROVIDER=anthropic AGENT_FABRIC_LAUNCH_EFFORT=low CLAUDE_EFFORT=low 2>&1)"
grep -q "^session effort low (confirmed)" <<<"$out" && ok "launched at a level below the routed one: the stamp is the headline" || bad "the headline is not the stamp" "$out"
# A session whose model expresses no effort has no level to report at all,
# and must not be given the code-high class's by recomputation.
printf '%s\n' '{"providers":{"anthropic":{"session":"claude-haiku-4-5-20251001"}}}' > "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROVIDER=anthropic 2>&1)"
! grep -q "^session effort" <<<"$out" && ok "a session model with no effort control reports none, not the class's" || bad "invented a session level" "$out"
rm -f "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(status AGENT_FABRIC_LAUNCH_ROLE=db-admin AGENT_FABRIC_LAUNCH_PROVIDER=anthropic AGENT_FABRIC_LAUNCH_EFFORT=max 2>&1)"
! grep -q "DRIFT.*effort" <<<"$out" && ok "no read-back at all: nothing to compare, nothing said" || bad "drift invented without CLAUDE_EFFORT" "$out"

echo "fabric-status: the account's placement"
HOSTS="$SANDBOX/hosts.json"
printf '{"version":1,"hosts":{"%s":{"platform":"fedora-qubes","ssh":null,"operator":"%s","fabric":"x"},"other-host":{"platform":"debian","ssh":"op@other","operator":"op","fabric":"x"}},"placement":{"%s":"%s"}}\n' "$(hostname -s)" "$LOGIN" "$LOGIN" "$(hostname -s)" > "$HOSTS"
out="$(status AGENT_FABRIC_HOSTS_REGISTRY="$HOSTS" 2>&1)"
! grep -q "registered on\|not placed" <<<"$out" && ok "placed on this host: no drift" || bad "false placement drift" "$out"
printf '{"version":1,"hosts":{"%s":{"platform":"fedora-qubes","ssh":null,"operator":"%s","fabric":"x"},"other-host":{"platform":"debian","ssh":"op@other","operator":"op","fabric":"x"}},"placement":{"%s":"other-host"}}\n' "$(hostname -s)" "$LOGIN" "$LOGIN" > "$HOSTS"
out="$(status AGENT_FABRIC_HOSTS_REGISTRY="$HOSTS" 2>&1)"
grep -q "^DRIFT        registered on other-host, running on $(hostname -s)" <<<"$out" && ok "placed elsewhere: one DRIFT line naming both hosts" || bad "placement drift not said" "$out"
MODE=(--json); out="$(status AGENT_FABRIC_HOSTS_REGISTRY="$HOSTS" 2>&1)"; MODE=()
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["placement"]=="other-host" and any("registered on other-host" in x for x in d["drift"])' <<<"$out" && ok "…and in the JSON report" || bad "json lacks placement" "$out"
printf '{"version":1,"hosts":{"%s":{"platform":"fedora-qubes","ssh":null,"operator":"%s","fabric":"x"}},"placement":{}}\n' "$(hostname -s)" "$LOGIN" > "$HOSTS"
out="$(status AGENT_FABRIC_HOSTS_REGISTRY="$HOSTS" 2>&1)"
grep -q "^DRIFT        not placed in runtime/hosts/registry.json" <<<"$out" && ok "not placed at all: said" || bad "missing placement not said" "$out"

echo "fabric-status: moveto installed from this repository, or behind it"
PREFIX="$SANDBOX/usr-local"
MOVETO_PREFIX="$PREFIX" sh "$ROOT/runtime/provisioning/moveto/install.sh" >/dev/null && ok "install.sh installs under \$MOVETO_PREFIX" || bad "install.sh failed"
[[ -s "$PREFIX/share/moveto/installed.sha256" ]] && ( cd "$PREFIX" && sha256sum -c --quiet share/moveto/installed.sha256 ) && ok "…and records a manifest that checks out" || bad "no manifest, or it does not check out"
out="$(status MOVETO_PREFIX="$PREFIX" 2>&1)"
grep -q "^moveto       in sync" <<<"$out" && ok "a fresh install is in sync" || bad "fresh install reported otherwise" "$out"
printf '\n# local edit\n' >> "$PREFIX/share/moveto/enter"
out="$(status MOVETO_PREFIX="$PREFIX" 2>&1)"
grep -q "^moveto       drift: behind the repository: share/moveto/enter" <<<"$out" && grep -q "edited in place since install: share/moveto/enter" <<<"$out" \
  && grep -q "install.sh" <<<"$out" && ok "an installed copy that differs is said, with the file, the cause and the fix" || bad "moveto drift not said" "$out"
MODE=(--json); out="$(status MOVETO_PREFIX="$PREFIX" 2>&1)"; MODE=()
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["host_tools"]["moveto"]["status"]=="drift"' <<<"$out" && ok "…and in the JSON report" || bad "json lacks host_tools" "$out"
out="$(status MOVETO_PREFIX="$SANDBOX/nowhere" 2>&1)"
! grep -q "^moveto" <<<"$out" && ok "no moveto under the prefix: no line" || bad "a line for an absent tool" "$out"

echo "fabric-status: memories written and not yet drained"
WC="$SANDBOX/gzapp"; git init -q "$WC"; git -C "$WC" remote add origin git@github.com:gzapi-org/gzapp.git
MEM="$SANDBOX/home/.claude/projects/$(printf '%s' "$WC" | sed 's/[^A-Za-z0-9]/-/g')/memory"   # the harness's spelling: every non-alphanumeric is a dash
mkdir -p "$MEM" "$WC/.agent-fabric/memory"
printf '{"watermarks":{"%s@%s":1000}}\n' "$(id -un)" "$(hostname -s)" > "$WC/.agent-fabric/memory/last-drain-report.json"
printf -- '---\nname: a\ndescription: d\nmetadata:\n  type: project\n  roles_class: solution\n---\nfact\n' > "$MEM/a.md"
printf -- '---\nname: b\ndescription: d\nmetadata:\n  type: user\n---\nmine\n' > "$MEM/b.md"
printf '# index\n' > "$MEM/MEMORY.md"
out="$(cd "$WC" && HOME="$SANDBOX/home" status 2>&1)"
grep -q "^memory       1 drainable (roles_class set) and 1 private (none) written since the last drain" <<<"$out" && ok "counts drainable and private memories newer than the watermark; MEMORY.md is not a memory" || bad "memory line wrong" "$out"
rm "$WC/.agent-fabric/memory/last-drain-report.json"
out="$(cd "$WC" && HOME="$SANDBOX/home" status 2>&1)"
grep -q "written since ever (no drain report)" <<<"$out" && ok "no report: counted since ever, said so" || bad "no-report case" "$out"
out="$(cd "$SANDBOX" && status 2>&1)"
! grep -q "^memory " <<<"$out" && ok "outside a working copy: no memory line" || bad "memory line without a working copy" "$out"

echo "fabric-status: the job list"
out="$(cd "$SANDBOX" && status 2>&1)"
grep -q "^jobs         none active; 0 queued, 0 blocked, 0 delivered" <<<"$out" && ok "an empty list: none active, zero counts" || bad "empty jobs line" "$(grep '^jobs' <<<"$out")"
(cd "$WC" && AGENT_FABRIC_ROOT="$ROOT" AGENT_FABRIC_STATE_DIR="$STATE" "$ROOT/bin/fabric-jobs" add "first" >/dev/null \
  && AGENT_FABRIC_ROOT="$ROOT" AGENT_FABRIC_STATE_DIR="$STATE" "$ROOT/bin/fabric-jobs" add "second" >/dev/null \
  && AGENT_FABRIC_ROOT="$ROOT" AGENT_FABRIC_STATE_DIR="$STATE" "$ROOT/bin/fabric-jobs" start j2 >/dev/null)
out="$(cd "$SANDBOX" && status 2>&1)"
grep -q "^jobs         active j2 (second); 1 queued, 0 blocked, 0 delivered" <<<"$out" && ok "the active job and the counts" || bad "jobs line" "$(grep '^jobs' <<<"$out")"
MODE=(--json); out="$(cd "$SANDBOX" && status 2>&1)"; MODE=()
python3 -c 'import json,sys; j=json.loads(sys.stdin.read())["jobs"]; assert j["active"]["id"]=="j2" and j["queued"]==1, j' <<<"$out" && ok "…and in --json" || bad "jobs json" "$out"

echo "fabric-status: which Claude sign-in plain claude uses"
H="$SANDBOX/signin-home"; mkdir -p "$H"
printf '{"oauthAccount":{"emailAddress":"someone@example.org"}}\n' > "$H/.claude.json"
out="$(status HOME="$H" 2>&1)"
grep -q "^claude sign-in own /login (someone@example.org)$" <<<"$out" && ok "no template token: the login's own sign-in, by its email" || bad "own sign-in line" "$(grep -i "sign-in" <<<"$out")"
TPL='sk-ant-oat01-TEMPLATE-FIXTURE'
FP="$(printf %s "$TPL" | sha256sum | cut -c1-12)"
out="$(status HOME="$H" CLAUDE_CODE_OAUTH_TOKEN="$TPL" 2>&1)"
grep -q "^claude sign-in setup-token $FP (CLAUDE_CODE_OAUTH_TOKEN" <<<"$out" && ! grep -q "someone@example.org" <<<"$out" \
  && ok "a template token outranks the own sign-in and is named by fingerprint, not by the old account" || bad "template sign-in line" "$(grep -i "sign-in" <<<"$out")"
! grep -q "$TPL" <<<"$out" && ok "the token itself is never printed" || bad "token printed"
# The shape that occurs: the launcher removed the variable from a broker
# session, so only the login's synced record says which account it is on.
mkdir -p "$H/.config/agent-fabric"; printf "export CLAUDE_CODE_OAUTH_TOKEN='%s'\n" "$TPL" > "$H/.config/agent-fabric/secrets.env"
out="$(status HOME="$H" ANTHROPIC_BASE_URL=https://openrouter.ai/api 2>&1)"
grep -q "^claude sign-in setup-token $FP .*(plain claude's; this session goes to broker (ori) and uses neither)$" <<<"$out" && ! grep -q "someone@example.org" <<<"$out" \
  && ok "a broker session on a template login names the template from the synced record, not the old account" || bad "broker sign-in line" "$(grep -i "sign-in" <<<"$out")"
! grep -q "$TPL" <<<"$out" && ! grep -q "^DRIFT.*setup-token" <<<"$out" && ok "…the token itself never printed, and no drift: the launcher removing it on the broker is the design" || bad "broker case" "$out"
# A direct-path session launched before the sync that moved the login: its
# environment has no token, the record has one. The line says which it
# reports, and the disagreement is drift, not the template claimed as in use.
out="$(status HOME="$H" 2>&1)"
grep -q "^claude sign-in setup-token $FP (the login's synced record;" <<<"$out" && grep -q "^DRIFT .*this session runs on no token, the login's synced record names setup-token $FP" <<<"$out" \
  && ok "direct path, record but no variable: named as the record, and said as drift" || bad "record without variable" "$(grep -iE "sign-in|DRIFT" <<<"$out")"
out="$(status HOME="$H" CLAUDE_CODE_OAUTH_TOKEN="$TPL" 2>&1)"
grep -q "^claude sign-in setup-token $FP (CLAUDE_CODE_OAUTH_TOKEN in this session;" <<<"$out" && ! grep -q "^DRIFT.*setup-token" <<<"$out" && ok "variable and record agree: this session's, no drift" || bad "agreeing case" "$(grep -iE "sign-in|DRIFT" <<<"$out")"
rm -f "$H/.config/agent-fabric/secrets.env"

echo
if [[ $FAIL -eq 0 ]]; then echo "test_fabric-status: OK — $PASS assertion(s) passed."; else echo "test_fabric-status: FAILED — $FAIL assertion(s) failed."; exit 1; fi
