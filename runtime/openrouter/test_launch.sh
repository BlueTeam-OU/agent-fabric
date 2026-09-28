#!/usr/bin/env bash
# runtime/openrouter/test_launch.sh
#
# Behavioural tests for runtime/openrouter/launch. The launcher execs a
# session, so the tests run it in SANDBOXES: a fake agent-fabric root (the
# real routing files minus the committed roles/agents layers, the real
# resolver), a fake state directory holding
# this agent's binding, a fake `ori` on PATH, and HOME pointed at a scratch
# dir. Every refusal, the merge order, the shim derivation and the
# review-grade gate are exercised without spawning a real claude.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAL_ROOT="$(cd "$HERE/../.." && pwd)"
LAUNCHER="$HERE/launch"
LOGIN="$(id -un)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ✓ %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  ✗ %s\n' "$1"; [[ -n "${2:-}" ]] && printf '%s\n' "$2" | sed 's/^/      /' | head -6; }

SANDBOX="$(mktemp -d)"; trap 'rm -rf "$SANDBOX"' EXIT
export HOME="$SANDBOX/home"; mkdir -p "$HOME"
# Every plain-claude launch needs a long-lived sign-in in the login's synced
# record; the fixture holds one of the right shape (never a real token).
SEC="$HOME/.config/agent-fabric/secrets.env"; mkdir -p "$(dirname "$SEC")"
printf "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-SUITE-FIXTURE'\n" > "$SEC"
mkdir -p "$SANDBOX/bin"
PATH_EXPORT="$SANDBOX/bin:$PATH"

# A fake ori whose auth --json reports environment-sourced auth and which
# records its argv and the child's environment when claude is called.
write_fake_ori() {
cat > "$SANDBOX/bin/ori" <<'FAKE'
#!/usr/bin/env bash
if [[ "${1:-}" == auth ]]; then
    echo '{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}'
    exit 0
fi
echo "ORI-EXECCED:$*"
# The child's ENVIRONMENT, not only its argv: a pin that lost its `export`
# would still print under --print and still be absent here.
for v in ANTHROPIC_DEFAULT_HAIKU_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_FABLE_MODEL AGENT_FABRIC_LAUNCH_SESSION_MODEL AGENT_FABRIC_LAUNCH_EFFORT AGENT_FABRIC_LAUNCH_PROFILE AGENT_FABRIC_LAUNCH_AGENT AGENT_FABRIC_LAUNCH_ROLE AGENT_FABRIC_LAUNCH_PROMPT_DIGEST AGENT_FABRIC_LAUNCH_CLAUDE_VERSION CLAUDE_CODE_DISABLE_TERMINAL_TITLE TMPDIR; do
    echo "ORI-ENV:$v=${!v:-}"
done
# Presence only, never a value: a template token must not reach the broker.
echo "ORI-HAS-OAUTH-TOKEN:${CLAUDE_CODE_OAUTH_TOKEN+yes}"
FAKE
chmod +x "$SANDBOX/bin/ori"
}
write_fake_ori

# A fixture agent-fabric root: the real routing files (minus the committed
# roles/agents layers) and resolver, a
# state dir with this agent's binding (role backend-dev), and a launch
# working copy with a real git toplevel.
FABRIC="$SANDBOX/fabric"; STATE="$SANDBOX/state"
mkfabric() {
    rm -rf "$FABRIC" "$STATE" "$SANDBOX/repo"
    mkdir -p "$FABRIC/runtime/openrouter" "$FABRIC/runtime/claude-code" "$FABRIC/tools/fabric" "$FABRIC/projects"
    cp -r "$REAL_ROOT/routing" "$FABRIC/routing"
    # The committed roles/agents layers are real routing, and one of them may
    # name the login running this suite; every layer a case tests it builds
    # with profile(), so the fixture starts from the defaults alone.
    python3 - "$FABRIC/routing/profiles.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["roles"], d["agents"] = {}, {}
json.dump(d, open(sys.argv[1], "w"), indent=2)
PY
    # Classes that differ, so a case can tell which one an export or an
    # agent file came from: the committed column is one model at one level.
    cp "$REAL_ROOT/tests/fixtures/routing-distinct/capabilities.json" "$REAL_ROOT/tests/fixtures/routing-distinct/effort.json" "$FABRIC/routing/"
    cp "$REAL_ROOT/runtime/claude-code/aliases.json" "$REAL_ROOT/runtime/claude-code/install-agent-files.sh" "$FABRIC/runtime/claude-code/"
    cp -r "$REAL_ROOT/runtime/claude-code/agents" "$FABRIC/runtime/claude-code/agents"
    mkdir -p "$FABRIC/runtime/mcp"; cp -r "$REAL_ROOT/runtime/mcp/websearch-locale" "$FABRIC/runtime/mcp/"   # the installer's MCP step reads its helper from the fabric
    cp "$REAL_ROOT/runtime/identity.py" "$FABRIC/runtime/"
    cp "$REAL_ROOT/tools/fabric/routing.py" "$REAL_ROOT/tools/fabric/workingcopy.py" "$REAL_ROOT/tools/fabric/jobs.py" "$FABRIC/tools/fabric/"
    # The role's system prompt: the assembler, the shared sections, and a
    # fixture charter for the bound role (no brief — the placeholder path).
    cp "$REAL_ROOT/tools/fabric/layout.py" "$REAL_ROOT/tools/fabric/launch_prompt.py" "$FABRIC/tools/fabric/"
    mkdir -p "$FABRIC/identities/roles/backend-dev"; cp -r "$REAL_ROOT/identities/prompt" "$FABRIC/identities/prompt"
    printf -- '---\nrole: backend-dev\nclass: charter\ndescription: "x"\ntier: 1\ndistilled_at: 2026-09-15\n---\n\n# backend-dev — charter\n\nFIXTURE-CHARTER-LINE: the backend that owns meaning.\n' > "$FABRIC/identities/roles/backend-dev/charter.md"
    cp "$REAL_ROOT/projects/registry.json" "$FABRIC/projects/"
    mkdir -p "$STATE/agents/$LOGIN"
    printf '{"agent":"%s","host":"'"$(hostname -s)"'","role":"backend-dev","updated_at":"x"}\n' "$LOGIN" > "$STATE/agents/$LOGIN/binding.json"
    mkdir -p "$SANDBOX/repo"; git init -q "$SANDBOX/repo"
}
# profile defaults '<json>'  |  profile roles <role> '<json>'  |  profile agents <login> '<json>'
profile() { python3 - "$FABRIC/routing/profiles.json" "$@" <<'PY'
import json, sys
path, layer = sys.argv[1], sys.argv[2]
d = json.load(open(path))
if layer == "defaults":
    d["defaults"].update(json.loads(sys.argv[3]))
else:
    key, body = sys.argv[3], json.loads(sys.argv[4])
    d.setdefault(layer, {})[key] = body
json.dump(d, open(path, "w"), indent=1)
PY
}
# TMPDIR is UNSET for the launcher unless a case says KEEP_TMPDIR=1: what
# is asserted below is the launcher's default (a per-login directory
# under /var/tmp), and a TMPDIR the caller set wins over it by design —
# tests/run.sh exports one for every suite, and passing it through made
# this test assert on the runner's directory rather than the launcher's.
# The credential family is CLEARED for every case, then re-set only from
# PLANT_<name>: a case that asserts about a base URL or a key must fix it
# itself, or its answer depends on where the suite runs. From inside a broker
# session the inherited OpenRouter URL once turned "an Anthropic key is left
# alone" red — pointing at the very clear that must stay (review of #31).
# OPENROUTER_API_KEY is not in the family: it is the account's own, and a
# case that needs a different one still sets it inline.
# CLAUDE_CONFIG_DIR rides the same mechanism: an inherited one pointed the
# launcher's install-agent-files and onboarding write at the runner's LIVE
# Claude config, outside the sandbox (review of #37, P-1). A case that
# needs one plants it.
CRED_FAMILY=(ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_CUSTOM_HEADERS CLAUDE_CONFIG_DIR)
run() {
    local strip=(-u TMPDIR); [[ -n "${KEEP_TMPDIR:-}" ]] && strip=()
    local plant=() v p
    for v in "${CRED_FAMILY[@]}"; do
        strip+=(-u "$v"); p="PLANT_$v"
        [[ -n "${!p+x}" ]] && plant+=("$v=${!p}")
    done
    (cd "$SANDBOX/repo" && env "${strip[@]}" "${plant[@]}" HOME="$HOME" PATH="$PATH_EXPORT" AGENT_FABRIC_ROOT="$FABRIC" AGENT_FABRIC_STATE_DIR="$STATE" bash "$LAUNCHER" "$@")
}
run_err() { run "$@" >/dev/null 2>&1; }

echo "launch: --print resolves the capability classes through model -> family shim"
mkfabric
out="$(run --print)"; rc=$?
[[ $rc -eq 0 ]] && ok "exits 0" || bad "rc=$rc" "$out"
grep -q "resolved profile for backend-dev/$LOGIN (agent $LOGIN, role backend-dev, provider openrouter)" <<<"$out" && ok "the label is role/agent, agent = login" || bad "label wrong" "$out"
grep -q "session : deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" <<<"$out" && ok "default session (the top tier, with its family shim)" || bad "session wrong" "$out"
grep -q "export ANTHROPIC_DEFAULT_HAIKU_MODEL=z-ai/glm-5.3-flash@preset/glm2claude-shim" <<<"$out" && ok "code-low -> glm-5.3-flash + shim -> haiku alias" || bad "code-low wrong" "$out"
grep -q "export ANTHROPIC_DEFAULT_SONNET_MODEL=z-ai/glm-5.2@preset/glm2claude-shim" <<<"$out" && ok "code-medium -> glm-5.2 + shim -> sonnet alias" || bad "code-medium wrong" "$out"
grep -q "export ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" <<<"$out" && ok "code-high -> deepseek v4 pro + its shim -> opus alias" || bad "code-high wrong" "$out"
grep -q "export ANTHROPIC_DEFAULT_FABLE_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim$" <<<"$out" && ok "code-plan -> deepseek v4 pro + its shim -> fable alias, its own export" || bad "code-plan (fable) wrong" "$out"
[[ "$(grep -c 'export ANTHROPIC_DEFAULT_' <<<"$out")" == 4 ]] && ok "four aliases, four exports: the review class never shares code-high's" || bad "export count" "$out"
# The alias exports above come from the same python block as the class
# lines, so a crash in it was already caught — but only by its exports.
# The class lines themselves, and the effort beside them, had nothing:
# the block could print every export and still get the per-class half
# wrong. These assert the half that no case reached, and that nothing
# reaches stderr (the launcher has no `set -e`, so a traceback there
# costs the caller nothing but the output it came for).
errf="$SANDBOX/print.err"; out="$(run --print 2>"$errf")"
[[ "$(grep -c '^  code-[a-z]*  *:' <<<"$out")" == 5 ]] && ok "a line per capability class, from the python block" || bad "class lines missing" "$out"
[[ ! -s "$errf" ]] && ok "…and --print writes nothing to stderr" || bad "--print wrote to stderr" "$(cat "$errf")"
[[ "$(grep -c '^  code-[a-z]*  *:.* effort ' <<<"$out")" == 5 ]] && ok "each class line carries its routed effort (routing/effort.json)" || bad "effort not printed per class" "$out"
grep -q "code-medium .* effort high (asked medium)" <<<"$out" && ok "a level the model does not admit prints asked -> served, never served alone" || bad "the broker downgrade is invisible" "$out"

echo "launch: a non-GLM override receives no shim; a GLM override keeps it"
mkfabric; profile roles backend-dev '{"capabilities":{"code-high":"anthropic/claude-sonnet-5"}}'
out="$(run --print)"
grep -q "export ANTHROPIC_DEFAULT_OPUS_MODEL=anthropic/claude-sonnet-5$" <<<"$out" && ok "a role override to a non-GLM model gets no shim" || bad "shim attached to a non-GLM model" "$out"
grep -q "export ANTHROPIC_DEFAULT_HAIKU_MODEL=z-ai/glm-5.3-flash@preset/glm2claude-shim" <<<"$out" && ok "the untouched GLM class keeps its shim" || bad "shim lost" "$out"
mkfabric; profile agents "$LOGIN" '{"capabilities":{"code-low":"z-ai/glm-5.2"},"session":"z-ai/glm-5.3"}'
out="$(run --print)"
grep -q "export ANTHROPIC_DEFAULT_HAIKU_MODEL=z-ai/glm-5.2@preset/glm2claude-shim" <<<"$out" && ok "an agent (login-keyed) override to another GLM model keeps the family shim" || bad "agent override ignored or unshimmed" "$out"
grep -q "session : z-ai/glm-5.3@preset/glm2claude-shim" <<<"$out" && ok "the session (main agent) gets the family shim too, separately from the classes" || bad "session shim wrong" "$out"

echo "launch: merge order — defaults <- role <- agent <- local, later wins"
mkfabric
profile defaults '{"capabilities":{"code-low":"vendor/default-low"}}'
profile roles backend-dev '{"capabilities":{"code-low":"vendor/role-low","code-medium":"vendor/role-medium"}}'
profile agents "$LOGIN" '{"capabilities":{"code-medium":"vendor/agent-medium"},"session":"vendor/agent-session"}'
printf '%s\n' '{"session":"vendor/local-session"}' > "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(run --print)"
grep -q "ANTHROPIC_DEFAULT_HAIKU_MODEL=vendor/role-low" <<<"$out" && ok "role row wins over defaults" || bad "role row ignored" "$out"
grep -q "ANTHROPIC_DEFAULT_SONNET_MODEL=vendor/agent-medium" <<<"$out" && ok "agent row wins over role" || bad "agent row ignored" "$out"
grep -q "session : vendor/local-session" <<<"$out" && ok "the local override wins over the agent row" || bad "local override ignored" "$out"

echo "launch: the review gate"
mkfabric; printf '%s\n' '{"capabilities":{"code-review":"anthropic/claude-opus-5"}}' > "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "code-review : anthropic/claude-opus-5  shim -  => anthropic/claude-opus-5  (pinned in the agent file" <<<"$out" && ! grep -q "ANTHROPIC_DEFAULT_FABLE_MODEL=anthropic/claude-opus-5" <<<"$out" && ok "another review-grade model in the local override is allowed; it reaches the reviewer file, never the fable export (code-plan's)" || bad "review-grade override refused" "$out"
grep -q "export ANTHROPIC_DEFAULT_FABLE_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" <<<"$out" && ok "the fable export is code-plan's" || bad "fable export not code-plan's" "$out"
mkfabric; printf '%s\n' '{"capabilities":{"code-review":"z-ai/glm-5.3-flash"}}' > "$STATE/agents/$LOGIN/model-profile.local.json"
run_err --print; [[ $? -ne 0 ]] && ok "a review model outside review-grade.json in the local override is REFUSED" || bad "review gate bypassed by local override"
mkfabric; printf '%s\n' '{"capabilities":{"code-high":"z-ai/glm-5.3-flash"}}' > "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "ANTHROPIC_DEFAULT_OPUS_MODEL=z-ai/glm-5.3-flash@preset/glm2claude-shim" <<<"$out" && ok "the coding classes are NOT review-gated: a cheap code-high is allowed" || bad "code-high wrongly gated" "$out"

echo "launch: the refusals"
mkfabric; rm "$STATE/agents/$LOGIN/binding.json"
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && grep -q "no active role binding" <<<"$out" && grep -q "bin/fabric-role bind" <<<"$out" && ok "no binding: refused, names bin/fabric-role" || bad "ran without a role" "$out"
mkfabric; printf '{"agent":"%s","host":"'"$(hostname -s)"'","role":null,"updated_at":"x"}\n' "$LOGIN" > "$STATE/agents/$LOGIN/binding.json"
run_err --print; [[ $? -eq 1 ]] && ok "binding with no role: refused" || bad "ran with a null role"
mkfabric; rm "$FABRIC/routing/capabilities.json"
run_err --print; [[ $? -eq 1 ]] && ok "no capabilities.json: refused" || bad "ran without the routing files"
mkfabric
out="$(run --settings foo.json)"; [[ $? -ne 0 ]] && ok "--settings passthrough refused" || bad "fence bypass allowed" "$out"
mkfabric; run_err --setting-sources user,project
[[ $? -ne 0 ]] && ok "--setting-sources passthrough refused" || bad "fence bypass allowed"
for flag in --system-prompt --system-prompt-file --append-system-prompt --append-system-prompt-file; do
    mkfabric; out="$(run $flag x.md 2>&1)"; rc=$?
    [[ $rc -ne 0 ]] && grep -q "role's system prompt is the" <<<"$out" && ok "$flag passthrough refused: the role's prompt is the launcher's" || bad "$flag admitted" "$out"
    mkfabric; run_err "$flag=x.md"; [[ $? -ne 0 ]] && ok "$flag=… refused too" || bad "$flag=… admitted"
done
mkfabric
mkdir -p "$HOME/.claude"
printf '%s\n' '{"env":{"ANTHROPIC_DEFAULT_OPUS_MODEL":"vendor/sneaky"}}' > "$HOME/.claude/settings.json"
run_err --print; [[ $? -eq 1 ]] && ok "user-scope ANTHROPIC_DEFAULT pin: refused" || bad "would race the profile"
rm -f "$HOME/.claude/settings.json"

# EVERY settings scope is fenced, and the refusal names the file and key.
pin_in() {  # pin_in <file> <json>
    mkfabric; mkdir -p "$(dirname "$1")"; printf '%s\n' "$2" > "$1"
    [[ -s "$1" ]] || { bad "fixture not written: $1"; rc=99; out=""; return; }
    out="$(run --print 2>&1)"; rc=$?
    rm -f "$1"
}
pin_in "$HOME/.claude/settings.local.json" '{"env":{"ANTHROPIC_DEFAULT_HAIKU_MODEL":"vendor/sneaky"}}'
[[ $rc -eq 1 ]] && ok "user LOCAL scope pin: refused" || bad "user local scope unfenced" "$out"
pin_in "$SANDBOX/repo/.claude/settings.json" '{"modelOverrides":{"claude-opus-5":"vendor/sneaky"}}'
[[ $rc -eq 1 ]] && ok "project scope modelOverrides: refused" || bad "project scope unfenced" "$out"
pin_in "$SANDBOX/repo/.claude/settings.local.json" '{"env":{"CLAUDE_CODE_SUBAGENT_MODEL":"vendor/sneaky"}}'
[[ $rc -eq 1 ]] && ok "project LOCAL scope subagent pin: refused" || bad "project local scope unfenced" "$out"
grep -q "settings.local.json carries model pins (env.CLAUDE_CODE_SUBAGENT_MODEL)" <<<"$out" && ok "…naming the file and the key" || bad "refusal does not name the offender" "$out"
mkdir -p "$SANDBOX/cfgdir"; mkfabric; printf '%s\n' '{"env":{"ANTHROPIC_MODEL":"vendor/sneaky"}}' > "$SANDBOX/cfgdir/settings.json"
out="$(PLANT_CLAUDE_CONFIG_DIR="$SANDBOX/cfgdir" run --print 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && ok "CLAUDE_CONFIG_DIR scope, ANTHROPIC_MODEL (not only _DEFAULT_): refused" || bad "config-dir scope unfenced" "$out"
rm -rf "$SANDBOX/cfgdir"
pin_in "$SANDBOX/repo/.claude/settings.local.json" '{"env":{"CLAUDE_BRIDGE_AUTH_TOKEN":"not-a-pin"},"model":"opus"}'
[[ $rc -eq 0 ]] && ok "a non-pin env entry and a top-level model preference are not refused" || bad "over-fenced" "$out"
mkfabric
out="$(CLAUDE_CODE_SUBAGENT_MODEL=vendor/sneaky run --print 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && ok "CLAUDE_CODE_SUBAGENT_MODEL in the caller's environment: refused" || bad "process-env subagent pin rides through" "$out"
mkfabric
out="$(CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1 run --print 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && grep -q "SUBAGENT_MODEL_FORCE" <<<"$out" && ok "CLAUDE_CODE_SUBAGENT_MODEL_FORCE: refused" || bad "FORCE rides through" "$out"
# The fence is on the LAUNCH directory, never an inherited REPO_ROOT.
mkfabric; rm -rf "$SANDBOX/other"; cp -r "$SANDBOX/repo" "$SANDBOX/other"
mkdir -p "$SANDBOX/repo/.claude"; printf '%s\n' '{"env":{"ANTHROPIC_DEFAULT_OPUS_MODEL":"vendor/sneaky"}}' > "$SANDBOX/repo/.claude/settings.local.json"
out="$(REPO_ROOT="$SANDBOX/other" run --print 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && grep -q "repo/.claude/settings.local.json carries model pins" <<<"$out" && ok "an inherited REPO_ROOT does not move the fence off the launch directory" || bad "inherited REPO_ROOT bypassed the launch dir's pin" "$out"
rm -rf "$SANDBOX/other"

echo "launch: identity comes from the OS, not from the directory or the environment"
mkfabric; rm -rf "$SANDBOX/repo"; mkdir -p "$SANDBOX/architect-cto-01"; git init -q "$SANDBOX/architect-cto-01"
out="$(cd "$SANDBOX/architect-cto-01" && env -u CLAUDE_CONFIG_DIR HOME="$HOME" PATH="$PATH_EXPORT" AGENT_FABRIC_ROOT="$FABRIC" AGENT_FABRIC_STATE_DIR="$STATE" USER=architect-cto-01 LOGNAME=architect-cto-01 bash "$LAUNCHER" --print 2>&1)"
grep -q "(agent $LOGIN, role backend-dev, provider openrouter)" <<<"$out" && ok "launched from a directory named for another agent, with USER forged: still agent $LOGIN" || bad "identity taken from directory or env" "$out"
mkdir -p "$SANDBOX/repo"; git init -q "$SANDBOX/repo"

# A malformed LOCAL override is refused, not exported as "None".
override() { mkfabric; printf '%s\n' "$1" > "$STATE/agents/$LOGIN/model-profile.local.json"; out="$(run --print 2>&1)"; rc=$?; }
override '{"session": null}'
[[ $rc -eq 1 ]] && grep -q "session is None" <<<"$out" && ok "session: null refused, named" || bad "None session accepted" "$out"
override '{"capabilities": {"code-low": null}}'
[[ $rc -eq 1 ]] && ok "capabilities.code-low: null refused" || bad "None class accepted" "$out"
override '{"capabilities": {"code-low": "Not A Model"}}'
[[ $rc -eq 1 ]] && ok "a class that is not a model id refused" || bad "prose accepted" "$out"
override '{"capabilities": {"code-low": ""}}'
[[ $rc -eq 1 ]] && ok "an empty class refused (ori would silently substitute its own default)" || bad "empty accepted" "$out"
override '{"capabilities": {"code-low": "z-ai/glm-5.3@preset/glm2claude-shim"}}'
[[ $rc -eq 1 ]] && ok "a COMPOSITE in a profile layer is refused: the shim is derived, never configured" || bad "composite accepted as canonical" "$out"
override '{"session": "anthropic/claude-opus-5:floor[1m]"}'
[[ $rc -eq 0 ]] && ok "variant and [1m] spellings accepted" || bad "valid ids refused" "$out"
override '{"session": "vendor/model\n"}'
[[ $rc -eq 1 ]] && grep -q "session is 'vendor/model\\\\n'" <<<"$out" && ok "a trailing newline is not a model id" || bad "regex stopped before the newline" "$out"

# --print anywhere in the arguments, not only first.
mkfabric
out="$(run --verbose --print 2>&1)"; rc=$?
grep -q "resolved profile" <<<"$out" && ! grep -q "ORI-EXECCED" <<<"$out" && ok "--print after another flag still prints, never execs" || bad "--print passed through to claude" "$out"

# Auth is a CONJUNCTION — authenticated AND source.kind == environment.
fake_auth() { printf '#!/usr/bin/env bash\necho %q\nexit %s\n' "$1" "${2:-0}" > "$SANDBOX/bin/ori"; chmod +x "$SANDBOX/bin/ori"; }
mkfabric; fake_auth '{"ok":false,"data":{"authenticated":false}}' 1
run_err --print; [[ $? -eq 1 ]] && ok "unauthenticated ori: refused" || bad "would exec into a prompt"
mkfabric; fake_auth '{"ok":true,"data":{"authenticated":false,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}'
run_err --print; [[ $? -eq 1 ]] && ok "unauthenticated but environment-sourced: refused" || bad "OR admitted an unauthenticated env key"
mkfabric; fake_auth '{"ok":true,"data":{"authenticated":true,"source":{"kind":"workspace"}}}'
run_err --print; [[ $? -eq 1 ]] && ok "authenticated from a stored credential: refused" || bad "non-environment source admitted"
mkfabric; fake_auth '{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment"}}}' 3
run_err --print; [[ $? -eq 1 ]] && ok "ori auth exit status is kept" || bad "non-zero ori auth ignored"
write_fake_ori

echo "launch: --provider anthropic execs plain claude with only the pinned tiers exported"
# A fake claude that records its argv and the four tier variables.
cat > "$SANDBOX/bin/claude" <<'FAKE'
#!/usr/bin/env bash
echo "CLAUDE-EXECCED:$*"
# Credentials by SHAPE, never by value: the suite runs with the account's
# real OPENROUTER_API_KEY in its environment, and a dump of a credential
# variable would put a secret in the suite's log.
for v in CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT CLAUDE_CODE_MAX_CONTEXT_TOKENS ANTHROPIC_MODEL DISABLE_TELEMETRY; do
    echo "CLAUDE-TUNE:$v=${!v-<unset>}"
done
for v in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_CUSTOM_HEADERS; do
    if [[ -z "${!v+x}" ]]; then shape=unset; elif [[ -z "${!v}" ]]; then shape=empty
    elif [[ "${!v}" == sk-or-* ]]; then shape=sk-or; elif [[ "${!v}" == sk-ant-* ]]; then shape=sk-ant; else shape=other; fi
    echo "CLAUDE-CRED:$v=$shape"
done
for v in ANTHROPIC_DEFAULT_HAIKU_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_FABLE_MODEL ANTHROPIC_BASE_URL AGENT_FABRIC_LAUNCH_SESSION_MODEL AGENT_FABRIC_LAUNCH_EFFORT AGENT_FABRIC_LAUNCH_PROVIDER AGENT_FABRIC_LAUNCH_PROFILE AGENT_FABRIC_LAUNCH_ROLE AGENT_FABRIC_LAUNCH_PROMPT_DIGEST AGENT_FABRIC_LAUNCH_CLAUDE_VERSION CLAUDE_CODE_DISABLE_TERMINAL_TITLE TMPDIR; do
    echo "CLAUDE-ENV:$v=${!v:-}"
done
FAKE
chmod +x "$SANDBOX/bin/claude"
mkfabric
out="$(run --provider anthropic --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && ok "--print exits 0" || bad "rc=$rc" "$out"
grep -q "provider anthropic)" <<<"$out" && ok "the header names the provider" || bad "provider not in header" "$out"
grep -q "session : claude-opus-5-5$" <<<"$out" && ok "the session is the anthropic default, Opus 5.5 (its own, not the broker's spelled natively)" || bad "session not the anthropic default" "$out"
grep -q "code-review : claude-opus-5\[1m\]  (pinned in the agent file; the dispatch guard applies it; from capabilities.providers.anthropic)" <<<"$out" && ok "the review class is pinned to claude-opus-5[1m] (the column's native id), through the agent file" || bad "review not pinned" "$out"
grep -q "code-high   : claude-opus-5-5  (exported for its tier; from capabilities.providers.anthropic)" <<<"$out" && grep -q "export ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5-5$" <<<"$out" && ok "a coding class pinned by the column is exported for the tier it rides (the top of each class)" || bad "column pin not exported" "$out"
grep -q "export ANTHROPIC_DEFAULT_FABLE_MODEL=claude-fable-5-1$" <<<"$out" && ok "the fable export is code-plan's pin; the reviewer never rides it" || bad "fable export wrong" "$out"

echo "launch: the session's effort — resolved, stamped, overridable, and never from the environment"
mkfabric
out="$(run --provider anthropic --print 2>&1)"
grep -q "^  effort  : high  (routing/effort.json)" <<<"$out" && ok "--print names the session level and where it came from" || bad "effort not printed for the session" "$out"
out="$(run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-EXECCED:.*--effort high" <<<"$out" && ok "…and it reaches claude as --effort" || bad "no --effort on the command line" "$out"
grep -q "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_EFFORT=high" <<<"$out" && ok "…and is stamped, so fabric-status can compare it with the read-back" || bad "no effort stamp in the child env" "$out"
# The stamp must say what the CHILD applies, never what the fabric wanted:
# the same rule --model already follows, and the reason fabric-status can
# treat a difference as drift at all.
out="$(run --provider anthropic --effort low --version 2>&1)"
grep -q "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_EFFORT=low" <<<"$out" && ok "a caller's --effort is what gets stamped" || bad "stamped the fabric's level over the caller's" "$out"
[[ "$(grep -c -- "--effort" <<<"$(grep CLAUDE-EXECCED <<<"$out")")" == 1 ]] && ok "…and only one --effort reaches the child" || bad "two --effort flags" "$out"
out="$(CLAUDE_CODE_EFFORT_LEVEL=max run --provider anthropic --version 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && ! grep -q "EXECCED" <<<"$out" && ok "CLAUDE_CODE_EFFORT_LEVEL in the environment: REFUSED, never launched" || bad "launched with an environment effort that outranks every class" "$out"
out="$(CLAUDE_CODE_EFFORT_LEVEL=auto run --provider anthropic --version 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && ok "…'auto' too: it is a value meaning 'use the model default', not an absence" || bad "auto admitted" "$out"
# Every scope the launcher fences for models, it must fence for effort:
# a settings key is merged into the CHILD, so it walks past the process
# environment refusal above.
mkfabric; mkdir -p "$HOME/.claude"
printf '%s\n' '{"maxEffortLevel":"low"}' > "$HOME/.claude/settings.json"
out="$(run --provider anthropic --version 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && ! grep -q "EXECCED" <<<"$out" && ok "a settings scope capping effort: REFUSED" || bad "launched under a settings maxEffortLevel" "$out"
printf '%s\n' '{"env":{"CLAUDE_CODE_EFFORT_LEVEL":"max"}}' > "$HOME/.claude/settings.json"
out="$(run --provider anthropic --version 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && ok "…and one carrying the variable in its env block" || bad "settings env walked past the process-env refusal" "$out"
# …but NOT the two the harness writes itself: `/effort` persists
# modelSettings into the user scope, and --effort outranks both, so
# refusing them would stop a launch on any account that used the command.
printf '%s\n' '{"modelSettings":{"claude-opus-5":{"effortLevel":"high"}},"effortLevel":"high"}' > "$HOME/.claude/settings.json"
out="$(run --provider anthropic --version 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "EXECCED" <<<"$out" && ok "a user scope carrying modelSettings/effortLevel still launches: --effort outranks them" || bad "refused what the harness writes itself" "$out"
rm -f "$HOME/.claude/settings.json"
out="$(CLAUDE_CODE_EFFORT_LEVEL= run --provider anthropic --version 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && ok "exported but EMPTY is still set, and still refused" || bad "an empty value was treated as unset" "$out"
# A trailing bare --effort is the caller's; adding ours makes the child
# read "--effort" as the level.
mkfabric
out="$(run --provider anthropic --version --effort 2>&1)"
[[ "$(grep -o -- "--effort" <<<"$(grep CLAUDE-EXECCED <<<"$out")" | wc -l)" == 1 ]] && ok "a trailing bare --effort is not doubled" || bad "two --effort tokens reached the child" "$out"

# A session on a model with no effort control gets no flag at all — absent
# is not the same as a default, and a stamp would invent a decision.
mkfabric; profile defaults '{"providers":{"anthropic":{"session":"claude-haiku-4-5-20251001"}}}'
out="$(run --provider anthropic --print 2>&1)"
grep -q "^  effort  : -  (this session's model expresses none" <<<"$out" && ok "a session model with no effort control says so" || bad "invented a level for a model without one" "$out"
# Planted, not inherited by accident: a launch from inside another fabric
# session arrives carrying that session's stamp, and must clear it rather
# than pass it on. CI has no stamp to inherit, so the case sets one.
out="$(AGENT_FABRIC_LAUNCH_EFFORT=high run --provider anthropic --version 2>&1)"
! grep -q -- "--effort" <<<"$out" && ! grep -q "AGENT_FABRIC_LAUNCH_EFFORT=." <<<"$out" && ok "…and passes no --effort and stamps nothing, even over an inherited stamp" || bad "passed an effort, or an inherited stamp, to a model that takes none" "$out"

python3 - "$FABRIC/routing/capabilities.json" <<'PY2'
import json, sys
d = json.load(open(sys.argv[1])); d["providers"]["anthropic"]["models"]["code-high"] = None
json.dump(d, open(sys.argv[1], "w"))
PY2
out="$(run --provider anthropic --print 2>&1)"; rc=$?
grep -q "code-high   : opus  (harness default for its tier)" <<<"$out" && ! grep -q "export ANTHROPIC_DEFAULT_OPUS_MODEL" <<<"$out" && ok "a null in the column is the harness's own tier: nothing exported for it" || bad "null column not the harness's" "$out"
# --print only shows the plan; the CHILD's environment is what runs. A
# launch from inside another fabric session arrives carrying that session's
# export for the alias, which would pin the "harness's own" tier to the
# parent's model. Planted, since CI has no parent to inherit from.
out="$(ANTHROPIC_DEFAULT_OPUS_MODEL=claude-parent-leftover run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-ENV:ANTHROPIC_DEFAULT_OPUS_MODEL=$" <<<"$out" && ok "…and an alias export inherited from a parent session is cleared, not passed on" || bad "the harness tier inherited the parent's pin" "$(grep OPUS <<<"$out")"
mkfabric; out="$(run --provider anthropic --print 2>&1)"; rc=$?
out="$(run --provider=anthropic --version 2>&1)"
grep -q "CLAUDE-EXECCED:--model claude-opus-5-5 --effort high --append-system-prompt-file $STATE/agents/$LOGIN/launch-prompt.md --version" <<<"$out" && ok "execs plain claude with the native session model and the role's prompt file" || bad "no plain-claude exec" "$out"
grep -q "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_ROLE=backend-dev$" <<<"$out" && ok "role stamped on plain claude" || bad "no role stamp" "$out"
! grep -q -- "--disallowedTools" <<<"$out" && ok "no tool removed from a login that is not language-culture" || bad "WebSearch removed from the wrong login" "$out"
# THE WATCH STARTS WITH THE SESSION: an interactive launch with no prompt
# of its own opens with one that arms it, after `--` and last, so no option
# of the caller's can take it as a value; print mode, the caller's own
# prompt, --version and a caller's own `--` add none (the owner, 2026-09-26).
out="$(run --provider anthropic 2>&1)"
grep -q "CLAUDE-EXECCED:.*launch-prompt.md -- Session start: arm your GZCoord inbox watch now, with Monitor(command: 'gzcoord-inbox --follow'" <<<"$out" && ok "a bare launch opens with the prompt that arms the watch, after --" || bad "no opening prompt on a bare launch" "$out"
out="$(run --provider anthropic --resume abc123 2>&1)"
grep -q "CLAUDE-EXECCED:.*--resume abc123 -- Session start: arm your GZCoord inbox watch" <<<"$out" && ok "…and a resume, after the session id" || bad "no opening prompt on a resume" "$out"
out="$(run --provider anthropic --resume 2>&1)"
grep -q "CLAUDE-EXECCED:.*--resume -- Session start: arm" <<<"$out" && ok "…a bare --resume keeps its picker: the prompt is not its value" || bad "the prompt became --resume's value" "$out"
out="$(run --provider anthropic --add-dir /x 2>&1)"
grep -q "CLAUDE-EXECCED:.*--add-dir /x -- Session start: arm" <<<"$out" && ok "…and a variadic option does not swallow it" || bad "a variadic option swallowed the prompt" "$out"
for a in "-p" "do-the-thing" "--version" "-- do-it" "--"; do
    out="$(run --provider anthropic $a </dev/null 2>&1)"
    ! grep -q "Session start: arm" <<<"$out" && ok "…none with: $a" || bad "opening prompt added with: $a" "$out"
done
out="$(AGENT_FABRIC_NO_OPENING=1 run --provider anthropic 2>&1)"
! grep -q "Session start: arm" <<<"$out" && ok "…and none when AGENT_FABRIC_NO_OPENING is set" || bad "opening prompt despite the switch" "$out"
# A language-culture login whose locale has a search: the harness's WebSearch is removed at exec.
mkdir -p "$FABRIC/identities/roles/language-culture"; cp -r "$FABRIC/identities/roles/backend-dev/." "$FABRIC/identities/roles/language-culture/"   # a charter to render
mkdir -p "$FABRIC/identities/roles/language-culture/locale/${LOGIN##*-}"; printf '{"timezone":"Asia/Tbilisi","brave":{"country":"ALL","tool_description":"ძიება"}}' > "$FABRIC/identities/roles/language-culture/locale/${LOGIN##*-}/locale.json"
printf '{"agent":"%s","host":"'"$(hostname -s)"'","role":"language-culture","updated_at":"x"}\n' "$LOGIN" > "$STATE/agents/$LOGIN/binding.json"
outlc="$(run --provider anthropic -- --version 2>&1)"
grep -q "CLAUDE-EXECCED:.*--version --disallowedTools WebSearch$" <<<"$outlc" && ok "a language-culture login with a locale search execs claude without WebSearch — the variadic flag last, after the caller's arguments" || bad "WebSearch not removed on the language-culture login, or not last" "$outlc"
outlc="$(run --provider anthropic 2>&1)"
grep -q "CLAUDE-EXECCED:.*--disallowedTools WebSearch -- Session start: arm" <<<"$outlc" && ok "…and a bare launch there: the opening after the variadic flag, behind --" || bad "the opening is not after --disallowedTools" "$outlc"
grep -q "CLAUDE-EXECCED:.*--append-system-prompt-file $STATE/agents/$LOGIN/launch-prompt.md" <<<"$outlc" && grep -q "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_CLAUDE_VERSION=$" <<<"$outlc" && ok "…with the prompt still appended and no build stamp: the locale carries no harness text" || bad "append expected without a harness translation" "$outlc"
# The build stamp means "the prompt is replaced". Inherited from a session
# whose prompt WAS replaced, it would say so of this child, whose prompt
# is only appended. Planted, since CI has nothing to inherit.
outlc="$(AGENT_FABRIC_LAUNCH_CLAUDE_VERSION="9.9.9 (Claude Code)" run --provider anthropic -- --version 2>&1)"
grep -q "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_CLAUDE_VERSION=$" <<<"$outlc" && ok "…and a build stamp inherited from a replaced session is cleared" || bad "an appended prompt inherited the replaced one's build stamp" "$(grep CLAUDE_VERSION <<<"$outlc")"
# The locale carries the harness text: the whole prompt is replaced, the build stamped, on both providers.
printf -- '---\nclass: harness-translation\ntranslates: runtime/claude-code/harness/en.md\ntranslates_digest: sha256:x\n---\nშენ ხარ Claude Code. მეხსიერება: `{memory_dir}`.\n' > "$FABRIC/identities/roles/language-culture/locale/${LOGIN##*-}/harness.md"
outlc="$(run --provider anthropic -- --version 2>&1)"
grep -q "CLAUDE-EXECCED:.*--system-prompt-file $STATE/agents/$LOGIN/launch-prompt.md" <<<"$outlc" && ! grep -q -- "--append-system-prompt-file" <<<"$outlc" && ok "a locale with the harness text execs claude with the whole prompt replaced" || bad "the prompt was not replaced" "$outlc"
grep -q "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_CLAUDE_VERSION=." <<<"$outlc" && ok "…and the build it ran is stamped" || bad "no build stamp on the replace branch" "$outlc"
grep -q "შენ ხარ Claude Code. მეხსიერება: \`$HOME/.claude/projects/" "$STATE/agents/$LOGIN/launch-prompt.md" && ! grep -q "{memory_dir}" "$STATE/agents/$LOGIN/launch-prompt.md" && ok "the rendered file ends with the harness text, its memory directory filled" || bad "harness text not rendered" "$(tail -3 "$STATE/agents/$LOGIN/launch-prompt.md")"
outp="$(run --provider anthropic --print 2>&1)"
grep -q "bytes; --system-prompt-file)" <<<"$outp" && grep -q "AGENT_FABRIC_LAUNCH_CLAUDE_VERSION=" <<<"$outp" && ok "--print names the flag and the build" || bad "--print does not name the replace" "$outp"
outori="$(run -- --version 2>&1)"
grep -q "ORI-EXECCED:claude .*--system-prompt-file $STATE/agents/$LOGIN/launch-prompt.md" <<<"$outori" && ok "the broker path carries the same flag" || bad "ori path lost the replace flag" "$outori"
rm -f "$FABRIC/identities/roles/language-culture/locale/${LOGIN##*-}/harness.md"
rm -rf "$FABRIC/identities/roles/language-culture/locale/${LOGIN##*-}"
outlc="$(run --provider anthropic -- --version 2>&1)"
! grep -q -- "--disallowedTools" <<<"$outlc" && ok "…and not when its locale has no search authored" || bad "WebSearch removed without a locale" "$outlc"
rm -rf "$FABRIC/identities/roles/language-culture"
printf '{"agent":"%s","host":"'"$(hostname -s)"'","role":"backend-dev","updated_at":"x"}\n' "$LOGIN" > "$STATE/agents/$LOGIN/binding.json"
grep -q "CLAUDE-ENV:CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1" <<<"$out" && ok "tab-title writer off on plain claude too" || bad "terminal-title switch missing on plain claude" "$out"
grep -q "CLAUDE-ENV:TMPDIR=/var/tmp/agent-fabric-$LOGIN" <<<"$out" && [[ -d "/var/tmp/agent-fabric-$LOGIN" && "$(stat -c %a "/var/tmp/agent-fabric-$LOGIN")" == 700 ]] && ok "TMPDIR is a per-login directory under /var/tmp, created 700" || bad "TMPDIR not exported under /var/tmp" "$out"
mkdir -p "$SANDBOX/own-tmp"
out2="$(KEEP_TMPDIR=1 TMPDIR="$SANDBOX/own-tmp" run --provider=anthropic --version 2>&1)"
grep -q "CLAUDE-ENV:TMPDIR=$SANDBOX/own-tmp" <<<"$out2" && ok "a TMPDIR the account set wins" || bad "the launcher overrode a set TMPDIR" "$out2"
! grep -q "ORI-EXECCED" <<<"$out" && ok "…not ori" || bad "went through ori" "$out"
grep -q "CLAUDE-ENV:ANTHROPIC_DEFAULT_FABLE_MODEL=claude-fable-5-1$" <<<"$out" && ok "FABLE exported as code-plan's pin, the native id" || bad "fable pin not in the child's env" "$out"
grep -q "CLAUDE-ENV:ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5-5$" <<<"$out" && ok "OPUS exported as code-high's pin" || bad "opus not in the child's env" "$out"
grep -q "^model: claude-opus-5\[1m\]$" "$HOME/.claude/agents/code-review.md" && ok "the exec installed the reviewer file for plain claude: claude-opus-5[1m]" || bad "reviewer file not installed for anthropic" "$(cat "$HOME/.claude/agents/code-review.md" 2>&1 | head -5)"
out="$(run --version 2>&1)"
grep -q "^model: deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim$" "$HOME/.claude/agents/code-review.md" && ok "…and a broker launch rewrites it with the composite: one file, one launch at a time" || bad "reviewer file not installed for the broker" "$(cat "$HOME/.claude/agents/code-review.md" 2>&1 | head -5)"
grep -q "^model: fable$" "$HOME/.claude/agents/code-plan.md" && ok "code-plan keeps its alias line: its pin is the export" || bad "code-plan file pinned" "$(head -5 "$HOME/.claude/agents/code-plan.md")"
out="$(run --provider=anthropic --version 2>&1)"
grep -q "CLAUDE-ENV:ANTHROPIC_BASE_URL=$" <<<"$out" && ok "no base URL: Anthropic direct" || bad "base URL set" "$out"
# The same assertion, over a base URL the CALLER carries: a launch started
# from inside a broker session inherits OpenRouter's, and without clearing
# it the child runs and bills on the broker while every stamp, --print and
# fabric-status says "anthropic". CI has none to inherit, so it is planted.
out="$(PLANT_ANTHROPIC_BASE_URL=https://openrouter.ai/api run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-ENV:ANTHROPIC_BASE_URL=$" <<<"$out" && ok "an inherited broker base URL is cleared on the anthropic path" || bad "the child inherited the broker's base URL while stamped anthropic" "$(grep -E 'BASE_URL|PROVIDER' <<<"$out")"
# …and ONLY the broker's. Any other base URL is someone's deliberate choice,
# never reviewed as such, so it is left exactly as it was.
out="$(PLANT_ANTHROPIC_BASE_URL=https://gateway.example.com run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-ENV:ANTHROPIC_BASE_URL=https://gateway.example.com$" <<<"$out" && ok "a base URL naming anything else is left alone" || bad "cleared a base URL that was not the broker's" "$(grep BASE_URL <<<"$out")"
out="$(PLANT_ANTHROPIC_BASE_URL=https://example.com/openrouter.ai run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-ENV:ANTHROPIC_BASE_URL=https://example.com/openrouter.ai$" <<<"$out" && ok "…including a look-alike with openrouter.ai in its path: the host decides" || bad "a look-alike path was read as the broker" "$(grep BASE_URL <<<"$out")"
# The CREDENTIALS, which is what the base URL alone missed. The environment
# `ori claude` gives its child, planted whole (read out of the ori binary):
# the base URL, an EMPTY auth token, and the OpenRouter key in
# ANTHROPIC_API_KEY. Clearing only the URL sent that key to Anthropic.
FAKE_OR=sk-or-v1-fixture-not-a-real-key
out="$(PLANT_ANTHROPIC_BASE_URL=https://openrouter.ai/api PLANT_ANTHROPIC_AUTH_TOKEN= PLANT_ANTHROPIC_API_KEY=$FAKE_OR OPENROUTER_API_KEY=$FAKE_OR PLANT_ANTHROPIC_CUSTOM_HEADERS='X-Session-Id: s1' run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-CRED:ANTHROPIC_API_KEY=unset" <<<"$out" && ok "the broker's key never reaches a plain-claude child" || bad "the OpenRouter key would go to Anthropic" "$(grep CLAUDE-CRED <<<"$out")"
grep -q "CLAUDE-CRED:ANTHROPIC_CUSTOM_HEADERS=unset" <<<"$out" && grep -q "CLAUDE-CRED:ANTHROPIC_AUTH_TOKEN=unset" <<<"$out" && ok "…nor its headers, nor its (empty) token" || bad "broker headers or token passed on" "$(grep CLAUDE-CRED <<<"$out")"
# The broker branch must clear the key BY ITSELF. Every key above is
# sk-or- shaped or equal to OPENROUTER_API_KEY, so the second check would
# catch them anyway and deleting ANTHROPIC_API_KEY from the branch's unset
# left the suite green. This key is neither: only the branch can clear it.
out="$(PLANT_ANTHROPIC_BASE_URL=https://openrouter.ai/api PLANT_ANTHROPIC_API_KEY=opaque-fixture-token OPENROUTER_API_KEY=a-different-value run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-CRED:ANTHROPIC_API_KEY=unset" <<<"$out" && ok "…the branch clears the key whatever its shape, with no second check to lean on" || bad "the broker branch left a key the secret check could not recognise" "$(grep CLAUDE-CRED <<<"$out")"
# Not only credentials: ori tunes its child for the BROKER'S model — a
# simplified system prompt, a context cap sized for that model — and a nested
# plain-claude launch inherited it. The privacy opt-outs are left: clearing
# them could switch telemetry back on against a person's own choice.
out="$(PLANT_ANTHROPIC_BASE_URL=https://openrouter.ai/api CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT=1 CLAUDE_CODE_MAX_CONTEXT_TOKENS=163840 ANTHROPIC_MODEL=deepseek/deepseek-v4-pro DISABLE_TELEMETRY=1 run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-TUNE:CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT=<unset>" <<<"$out" && grep -q "CLAUDE-TUNE:CLAUDE_CODE_MAX_CONTEXT_TOKENS=<unset>" <<<"$out" && grep -q "CLAUDE-TUNE:ANTHROPIC_MODEL=<unset>" <<<"$out" && ok "the broker's model tuning does not follow onto plain claude" || bad "broker tuning inherited" "$(grep CLAUDE-TUNE <<<"$out")"
grep -q "CLAUDE-TUNE:DISABLE_TELEMETRY=1" <<<"$out" && ok "…but a privacy opt-out is left as it was" || bad "a privacy opt-out was cleared" "$(grep CLAUDE-TUNE <<<"$out")"
grep -q "^launch: plain claude goes to Anthropic direct — dropped .*ANTHROPIC_BASE_URL.*CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT" <<<"$out" && ok "…and what was dropped is said, by name" || bad "the drop was silent" "$(grep '^launch:' <<<"$out")"
! grep -qE "openrouter.ai/api|163840|deepseek/deepseek-v4-pro" <<<"$(grep '^launch:' <<<"$out")" && ok "…names only, never values" || bad "the drop notice printed a value" "$(grep '^launch:' <<<"$out")"
# Without a broker base URL, the same variables are someone's own: kept, silently.
out="$(CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT=1 run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-TUNE:CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT=1" <<<"$out" && ! grep -q "^launch: plain claude goes" <<<"$out" && ok "with no broker base URL the tuning is a person's own: kept, and nothing said" || bad "cleared or announced a setting with no broker beside it" "$(grep -E 'CLAUDE-TUNE|^launch:' <<<"$out")"
# The secret check stands on its own, without the base URL beside it.# The secret check stands on its own, without the base URL beside it.# The secret check stands on its own, without the base URL beside it.
out="$(PLANT_ANTHROPIC_API_KEY=$FAKE_OR OPENROUTER_API_KEY=$FAKE_OR run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-CRED:ANTHROPIC_API_KEY=unset" <<<"$out" && ok "an OpenRouter key in ANTHROPIC_API_KEY is dropped even with no broker base URL" || bad "the OR key survived without its base URL" "$(grep CLAUDE-CRED <<<"$out")"
# OPENROUTER_API_KEY set to something ELSE, so equality cannot fire and
# only the shape can clear it.
out="$(OPENROUTER_API_KEY=a-different-value PLANT_ANTHROPIC_API_KEY=$FAKE_OR run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-CRED:ANTHROPIC_API_KEY=unset" <<<"$out" && ok "…recognised by its shape alone, when it matches no known key" || bad "an sk-or key went through" "$(grep CLAUDE-CRED <<<"$out")"
# And ONLY that: a real Anthropic key is the person's own and passes on.
out="$(PLANT_ANTHROPIC_API_KEY=sk-ant-fixture-not-a-real-key run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-CRED:ANTHROPIC_API_KEY=sk-ant" <<<"$out" && ok "an Anthropic key is left alone" || bad "dropped an Anthropic key" "$(grep CLAUDE-CRED <<<"$out")"
out="$(PLANT_ANTHROPIC_BASE_URL=https://gateway.example.com PLANT_ANTHROPIC_API_KEY=sk-ant-fixture-not-a-real-key run --provider anthropic --version 2>&1)"
grep -q "CLAUDE-CRED:ANTHROPIC_API_KEY=sk-ant" <<<"$out" && ok "…including beside a non-broker base URL" || bad "dropped a gateway user's key" "$(grep CLAUDE-CRED <<<"$out")"
grep -q "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_PROVIDER=anthropic" <<<"$out" && ok "provider stamped" || bad "no provider stamp" "$out"
grep -q "CLAUDE-ENV:AGENT_FABRIC_LAUNCH_PROFILE=backend-dev/$LOGIN" <<<"$out" && ok "profile stamped on vanilla too" || bad "no profile stamp" "$out"
mkfabric
rm -f "$STATE/agents/$LOGIN/binding.json"
out="$(run --provider anthropic --print 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && grep -q "no active role binding" <<<"$out" && ok "vanilla through the launcher still needs a bound role" || bad "unbound vanilla launch admitted" "$out"
mkfabric
profile defaults '{"session": "z-ai/glm-5.3", "providers": {}}'
out="$(run --provider anthropic --print 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && grep -q "not an Anthropic model and no profile layer names one" <<<"$out" && ok "a non-Anthropic session with no Anthropic layer is refused on vanilla, not mistranslated" || bad "foreign session admitted" "$out"
# A layer is per provider: plain claude's session and pins are named in
# its own vocabulary (the class, a native id) and never leak to the broker.
mkfabric
printf '%s\n' '{"providers":{"openrouter":{"session":"z-ai/glm-5.3"},"anthropic":{"session":"code-plan","capabilities":{"code-high":"claude-opus-5[1m]","code-low":"claude-haiku-4-5"}}}}' > "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(run --provider anthropic --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "session : claude-fable-5-1  (the code-plan class)" <<<"$out" && ! grep -q "is not an Anthropic model" <<<"$out" && ok "plain claude's session is providers.anthropic.session, a class, resolved on this provider, with no skip to report" || bad "per-provider session not honoured" "$out"
grep -q "code-high   : claude-opus-5\[1m\]  (exported for its tier; from local)" <<<"$out" && grep -q "export ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5\[1m\]" <<<"$out" && ok "a local pin of a coding class is exported for the tier it rides and says where it came from" || bad "local pin not exported" "$out"
grep -q "export ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-haiku-4-5$" <<<"$out" && grep -q "export ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-5$" <<<"$out" && ok "the other tiers keep the column's pins" || bad "column pins lost under a local layer" "$out"
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "session : z-ai/glm-5.3@preset/glm2claude-shim" <<<"$out" && grep -q "export ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" <<<"$out" && ok "the same file on the broker: its own session, and the native pins do not reach the broker's exports" || bad "anthropic layer leaked to the broker" "$out"
printf '%s\n' '{"session":"code-high"}' > "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "session : deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim  (the code-high class)" <<<"$out" && ok "a flat class-named session is that class's composite on the broker" || bad "class session on the broker" "$out"
out="$(run --provider anthropic --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "session : claude-opus-5-5  (the code-high class)" <<<"$out" && ok "…and that class's native pin on plain claude" || bad "class session on vanilla" "$out"
printf '%s\n' '{"providers":{"anthropic":{"capabilities":{"code-review":"claude-haiku-4-5"}}}}' > "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(run --provider anthropic --print 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && grep -q "not in routing/policies/review-grade.json" <<<"$out" && ok "a local review pin outside the grade is refused on vanilla" || bad "ungraded local review pin admitted" "$out"
printf '%s\n' '{"providers":{"anthropic":{"capabilities":{"code-high":"z-ai/glm-5.3"}}}}' > "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(run --provider anthropic --print 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && grep -q "providers.anthropic.capabilities.code-high is 'z-ai/glm-5.3', not a native Claude id" <<<"$out" && ok "a class pinned to a broker id on plain claude is refused by name" || bad "wrong vocabulary admitted" "$out"
out="$(run --print 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && ok "…on the broker path too: one malformed layer refuses every launch" || bad "malformed anthropic layer admitted on the broker" "$out"
printf '%s\n' '{"providers":{"anthropic":{"capabilities":{"code-high":"opus"}}}}' > "$STATE/agents/$LOGIN/model-profile.local.json"
out="$(run --provider anthropic --print 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && grep -q "not a native Claude id" <<<"$out" && ok "a tier alias is not a model: the class is the vocabulary, the alias is the adapter's" || bad "alias admitted as a model" "$out"
mkfabric
python3 - "$FABRIC/routing/capabilities.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["providers"]["anthropic"]["models"]["code-review"] = "claude-haiku-4-5"
json.dump(d, open(sys.argv[1], "w"))
PY
out="$(run --provider anthropic --print 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && grep -q "not in routing/policies/review-grade.json" <<<"$out" && ok "a pinned review model outside the grade is refused on vanilla too" || bad "ungraded vanilla review admitted" "$out"
out="$(run --provider nowhere --print 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && grep -q "must be openrouter or anthropic" <<<"$out" && ok "an unknown provider is refused" || bad "unknown provider admitted" "$out"
rm -f "$SANDBOX/bin/claude"

echo "launch: the exec carries the pins to the child"
mkfabric
out="$(run --version 2>&1)"; rc=$?
grep -q "ORI-EXECCED:" <<<"$out" && ok "execs via ori claude" || bad "no exec" "$out"
grep -q -- "--model deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" <<<"$out" && ok "session model passed as --model" || bad "session missing" "$out"
grep -q "ORI-ENV:ANTHROPIC_DEFAULT_HAIKU_MODEL=z-ai/glm-5.3-flash@preset/glm2claude-shim" <<<"$out" && ok "HAIKU pin (code-low composite) is in the child's environment" || bad "haiku pin not exported" "$out"
grep -q "ORI-ENV:ANTHROPIC_DEFAULT_SONNET_MODEL=z-ai/glm-5.2@preset/glm2claude-shim" <<<"$out" && ok "SONNET pin (code-medium composite) is in the child's environment" || bad "sonnet pin not exported" "$out"
grep -q "ORI-ENV:ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" <<<"$out" && ok "OPUS pin (code-high composite) is in the child's environment" || bad "opus pin not exported" "$out"
grep -q "ORI-ENV:ANTHROPIC_DEFAULT_FABLE_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim$" <<<"$out" && ok "FABLE pin (code-plan composite) is in the child's environment, separate from OPUS" || bad "fable pin not exported" "$out"
grep -q "ORI-ENV:AGENT_FABRIC_LAUNCH_SESSION_MODEL=deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim" <<<"$out" && ok "session model stamped in the child env" || bad "no session stamp" "$out"
grep -q "ORI-ENV:AGENT_FABRIC_LAUNCH_PROFILE=backend-dev/$LOGIN" <<<"$out" && ok "profile stamped as role/agent" || bad "no profile stamp" "$out"
grep -q "ORI-ENV:AGENT_FABRIC_LAUNCH_AGENT=$LOGIN" <<<"$out" && ok "agent stamped" || bad "no agent stamp" "$out"
grep -q "ORI-ENV:CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1" <<<"$out" && ok "the harness's tab-title writer is off in the child: the hook is the only writer" || bad "terminal-title switch not in the child's env" "$out"
mkfabric
out="$(run --model vendor/override --version 2>&1)"
grep -q "ORI-ENV:AGENT_FABRIC_LAUNCH_SESSION_MODEL=vendor/override" <<<"$out" && ok "a caller's --model is what gets stamped" || bad "stamp disagrees with argv" "$out"
grep -q "ORI-EXECCED:claude --effort high --append-system-prompt-file $STATE/agents/$LOGIN/launch-prompt.md --model vendor/override --version" <<<"$out" && ! grep -q -- "--model anthropic/claude-sonnet-5" <<<"$out" && ok "…and the launcher's own --model is omitted, so the child sees one; the prompt file still rides" || bad "two --model flags reached the child, or no prompt file" "$out"
mkfabric
out="$(run --print --model=vendor/override2 2>&1)"
grep -q "overridden by --model on the command line: vendor/override2" <<<"$out" && ok "--print shows the override" || bad "--print hides the override" "$out"
mkfabric
out="$(run -p hi 2>&1)"
grep -q "ORI-EXECCED:claude --model deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim --effort high --append-system-prompt-file $STATE/agents/$LOGIN/launch-prompt.md -p hi" <<<"$out" && ok "-p passes through to claude untouched, after the prompt file" || bad "-p swallowed by the launcher" "$out"

echo "launch: a Claude-account template's token never reaches a broker session"
mkfabric
out="$(CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-TEMPLATE-FIXTURE run --version 2>&1)"
grep -q "^ORI-HAS-OAUTH-TOKEN:$" <<<"$out" && grep -q "dropped CLAUDE_CODE_OAUTH_TOKEN" <<<"$out" && ok "broker path: the template token is dropped before the session, and that is said" || bad "template token reached the broker" "$(grep -i oauth <<<"$out")"
! grep -q "sk-ant-oat01-TEMPLATE-FIXTURE" <<<"$out" && ok "…by name, never by value" || bad "token value printed"
# On plain claude the login's synced record decides, not the inherited shell.
# A fake claude of its own (the plain-claude block above removed its fake):
# it reports the token it was given by fingerprint only.
cat > "$SANDBOX/bin/claude" <<'FAKE'
#!/usr/bin/env bash
v="${CLAUDE_CODE_OAUTH_TOKEN:-}"; if [ -n "$v" ]; then echo "CLAUDE-OAUTH-SHA:$(printf %s "$v" | sha256sum | cut -c1-12)"; else echo "CLAUDE-OAUTH-SHA:none"; fi
FAKE
chmod +x "$SANDBOX/bin/claude"
fp() { printf %s "$1" | sha256sum | cut -c1-12; }
printf "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-NEW-TEMPLATE'\n" > "$SEC"
out="$(CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-OLD-TEMPLATE run --provider anthropic --version 2>&1)"
grep -q "^CLAUDE-OAUTH-SHA:$(fp sk-ant-oat01-NEW-TEMPLATE)$" <<<"$out" && grep -q "taken from the login's synced record" <<<"$out" \
  && ok "plain claude: the synced record's token, not the older one the shell inherited, and that is said" || bad "stale inherited token used" "$(grep -iE "oauth|synced" <<<"$out")"
! grep -q "sk-ant-oat01-" <<<"$out" && ok "…by name, never by value" || bad "token value printed"
: > "$SEC"
rc=0; out="$(CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-OLD-TEMPLATE run --provider anthropic --version 2>&1)" || rc=$?
grep -q "the login's synced record has none" <<<"$out" && ok "no template in the record: an inherited one is dropped, by name" || bad "inherited token kept" "$(grep -iE "oauth|synced" <<<"$out")"
[[ $rc -eq 1 ]] && grep -q "no long-lived Claude sign-in" <<<"$out" && ! grep -q "^CLAUDE-OAUTH-SHA:" <<<"$out" \
  && ok "…and the launch is refused: no session on a login's own /login" || bad "launched without a long-lived sign-in" "rc=$rc $(grep -iE "oauth|sign-in" <<<"$out")"
printf "export CLAUDE_CODE_OAUTH_TOKEN='a-login-access-token'\n" > "$SEC"
rc=0; out="$(run --provider anthropic --version 2>&1)" || rc=$?
[[ $rc -eq 1 ]] && grep -q "no long-lived Claude sign-in" <<<"$out" && ok "a token not of a setup-token's shape is refused too" || bad "a malformed token launched" "rc=$rc"
printf "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-SUITE-FIXTURE'\n" > "$SEC"
printf '{"hasCompletedOnboarding": false, "theme": "dark"}\n' > "$HOME/.claude.json"
out="$(run --provider anthropic --version 2>&1)"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('hasCompletedOnboarding') is True and d.get('theme') == 'dark' else 1)" "$HOME/.claude.json" && grep -q "marked the harness's onboarding done" <<<"$out" \
  && ok "a template login's unfinished onboarding is marked done before the session — the wizard would ask for a /login" || bad "onboarding left unfinished" "$(cat "$HOME/.claude.json")"
out="$(run --provider anthropic --version 2>&1)"
! grep -q "marked the harness's onboarding done" <<<"$out" && ok "…once: an onboarded login's file is not rewritten" || bad "rewrote an onboarded file"
rm -f "$HOME/.claude.json"
: > "$SEC"
rc=0; out="$(run --provider anthropic --print 2>&1)" || rc=$?
[[ $rc -eq 0 ]] && ok "--print needs no sign-in: a prompt read-back still works" || bad "--print refused without a sign-in" "rc=$rc $(tail -2 <<<"$out")"
printf "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-SUITE-FIXTURE'\n" > "$SEC"
rm -f "$SANDBOX/bin/claude"

echo "launch: announces nothing — presence is the control plane's; the session's exit status is still the launcher's"
# A tripwire: a stub announce.py that records any call, in the place the
# launcher used to call it from; the binding names a project, which is what
# once made it announce. Nothing may be sent.
mkfabric
printf '{"agent":"%s","host":"'"$(hostname -s)"'","role":"backend-dev","project":"gzapp","updated_at":"x"}\n' "$LOGIN" > "$STATE/agents/$LOGIN/binding.json"
cat > "$FABRIC/tools/fabric/announce.py" <<'STUB'
import os, sys, time
with open(os.environ["ANNOUNCE_LOG"], "a") as fh:
    fh.write(" ".join(sys.argv[1:]) + f" @{time.time():.3f}\n")
STUB
ALOG="$SANDBOX/announce.log"; rm -f "$ALOG"
runa() { (cd "$SANDBOX/repo" && env -u CLAUDE_CONFIG_DIR HOME="$HOME" PATH="$PATH_EXPORT" AGENT_FABRIC_ROOT="$FABRIC" AGENT_FABRIC_STATE_DIR="$STATE" ANNOUNCE_LOG="$ALOG" bash "$LAUNCHER" "$@"); }
out="$(runa --version 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && ok "the launcher's exit status is the session's (0)" || bad "rc=$rc" "$out"
[[ ! -s "$ALOG" ]] && ok "nothing announced before the session or after it (HELLO and GOODBYE are retired)" || bad "the launcher announced" "$(cat "$ALOG")"
# A plain-claude launch refused for want of a long-lived sign-in announces
# nothing. Its own fake claude: the one above is gone, and a runner has no
# real harness on PATH for the launcher's earlier checks to find (CI, #37).
printf '#!/usr/bin/env bash\necho "CLAUDE-RAN"\n' > "$SANDBOX/bin/claude"; chmod +x "$SANDBOX/bin/claude"
: > "$SEC"; rm -f "$ALOG"
rc=0; out="$(runa --provider anthropic --version 2>&1)" || rc=$?
[[ $rc -eq 1 ]] && grep -q "no long-lived Claude sign-in" <<<"$out" && ! grep -q "CLAUDE-RAN" <<<"$out" && [[ ! -s "$ALOG" ]] \
  && ok "a launch refused for want of a long-lived sign-in starts nothing and announces nothing" || bad "a refused launch announced itself" "rc=$rc $(tail -3 <<<"$out") $(cat "$ALOG" 2>/dev/null)"
printf "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-SUITE-FIXTURE'\n" > "$SEC"; rm -f "$ALOG" "$SANDBOX/bin/claude"
# The session's failure is the launcher's failure.
cat > "$SANDBOX/bin/ori" <<'FAKE'
#!/usr/bin/env bash
if [[ "${1:-}" == auth ]]; then echo '{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}'; exit 0; fi
echo "ORI-EXECCED:$*"; exit 3
FAKE
chmod +x "$SANDBOX/bin/ori"; rm -f "$ALOG"
out="$(runa --version 2>&1)"; rc=$?
[[ $rc -eq 3 ]] && ok "a session exiting 3 makes the launcher exit 3" || bad "rc=$rc" "$out"
[[ ! -s "$ALOG" ]] && ok "…and announces nothing" || bad "announced after status 3" "$(cat "$ALOG")"
# A session killed by a signal — what a double Ctrl-C or a kill leaves — is the launcher's status too.
cat > "$SANDBOX/bin/ori" <<'FAKE'
#!/usr/bin/env bash
if [[ "${1:-}" == auth ]]; then echo '{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}'; exit 0; fi
echo "ORI-EXECCED:$*"; kill -TERM $$
FAKE
chmod +x "$SANDBOX/bin/ori"; rm -f "$ALOG"
out="$(runa --version 2>&1)"; rc=$?
[[ $rc -eq 143 ]] && ok "a session ended by SIGTERM: the launcher reports 143" || bad "rc=$rc" "$out"
[[ ! -s "$ALOG" ]] && ok "…and announces nothing" || bad "announced after SIGTERM" "$(cat "$ALOG")"
write_fake_ori

echo "launch: a session stopped for an upgrade comes back, resumed, on the new version"
# The fake session plays the control agent's part: on its first run it
# writes the restart marker as upgrade.mjs does and ends as SIGTERM leaves
# it (143); on the second it records its arguments. The binding names the
# session id the restart must resume.
printf '{"agent":"%s","host":"'"$(hostname -s)"'","role":"backend-dev","project":"gzapp","session":"sess-123","updated_at":"x"}\n' "$LOGIN" > "$STATE/agents/$LOGIN/binding.json"
upgrade_session() {  # upgrade_session <marker status> <requested_at>
cat > "$SANDBOX/bin/ori" <<FAKE
#!/usr/bin/env bash
if [[ "\${1:-}" == auth ]]; then echo '{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}'; exit 0; fi
n="\$(cat "$SANDBOX/runs" 2>/dev/null || echo 0)"; echo \$((n+1)) > "$SANDBOX/runs"
if [[ "\$n" == 0 ]]; then
  printf '{"request_id":"r1","requested_at":"%s","piece":"claude","from":"2.1.280","to":"2.1.281","installed":"2.1.281","status":"%s","reason":"network"}\\n' "$2" "$1" > "$STATE/agents/$LOGIN/restart.json"
  echo "RUN1:\$*"; exit 143
fi
echo "RUN2:\$*"; exit 0
FAKE
chmod +x "$SANDBOX/bin/ori"; rm -f "$SANDBOX/runs" "$ALOG"
}
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; sleep 1; NOW2="$(date -u -d '+1 second' +%Y-%m-%dT%H:%M:%SZ)"
upgrade_session done "$NOW2"
out="$(runa --resume old-id --model x 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "claude upgraded 2.1.280 → 2.1.281; resuming the session on it" <<<"$out" && ok "the upgrade is said, and the launcher does not exit with the stopped session" || bad "no restart (rc=$rc)" "$out"
grep -q "^RUN2:.*--model x" <<<"$out" && grep -q "^RUN2:.*--resume sess-123" <<<"$out" && ! grep -q "^RUN2:.*old-id" <<<"$out" \
  && ok "…resumed by the stopped session's id; the caller's own --resume replaced, the rest passed on" || bad "resume args" "$(grep RUN2 <<<"$out")"
[[ ! -e "$STATE/agents/$LOGIN/restart.json" ]] && ok "…and the marker is consumed" || bad "marker left behind"
[[ ! -s "$ALOG" ]] && ok "…and a stop and resume announce nothing either" || bad "announced across a restart" "$(cat "$ALOG")"
upgrade_session failed "$(date -u -d '+5 seconds' +%Y-%m-%dT%H:%M:%SZ)"
out="$(runa 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "FAILED (network); resuming the session on what is installed" <<<"$out" && grep -q "^RUN2:.*--resume sess-123" <<<"$out" && ok "a failed upgrade still brings the session back, and says why" || bad "failed upgrade" "$out"
upgrade_session pending "$(date -u -d '+5 seconds' +%Y-%m-%dT%H:%M:%SZ)"
out="$(AGENT_FABRIC_RESTART_WAIT_S=1 runa 2>&1)"; rc=$?
grep -q "waiting for it" <<<"$out" && grep -q "did not finish within 1 s; resuming" <<<"$out" && grep -q "^RUN2:" <<<"$out" && ok "an upgrade that never finishes: the wait is bounded, the session comes back" || bad "pending wait" "$out"
upgrade_session done "2026-01-01T00:00:00Z"
out="$(runa 2>&1)"; rc=$?
[[ $rc -eq 143 ]] && ! grep -q "^RUN2:" <<<"$out" && [[ ! -e "$STATE/agents/$LOGIN/restart.json" ]] && ok "a marker older than the launch is another session's: removed, not obeyed" || bad "stale marker obeyed (rc=$rc)" "$out"
write_fake_ori

echo "launch: a session that ends its own job comes back fresh, not resumed"
# The fake session plays bin/fabric-fresh: a marker with fresh true and a
# note, then the stop; the relaunch must name no session and say the note.
cat > "$SANDBOX/bin/ori" <<FAKE
#!/usr/bin/env bash
if [[ "\${1:-}" == auth ]]; then echo '{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}'; exit 0; fi
n="\$(cat "$SANDBOX/runs" 2>/dev/null || echo 0)"; echo \$((n+1)) > "$SANDBOX/runs"
if [[ "\$n" == 0 ]]; then
  printf '{"requested_at":"%s","piece":"a fresh session","status":"done","fresh":true,"note":"PR 981 merged"}\\n' "\$(date -u -d '+2 seconds' +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/agents/$LOGIN/restart.json"
  echo "RUN1:opening=\${AGENT_FABRIC_LAUNCH_OPENING:-unset}:\$*"; exit 143
fi
echo "RUN2:\$*"; exit 0
FAKE
chmod +x "$SANDBOX/bin/ori"; rm -f "$SANDBOX/runs"
out="$(runa --resume old-id 2>&1)"; rc=$?
grep -q "^RUN1:opening=1:" <<<"$out" && ok "the session is told the launcher wrote its opening (fabric-fresh reads it)" || bad "no opening flag" "$(grep RUN1 <<<"$out")"
[[ $rc -eq 0 ]] && grep -q "the session finished its job: PR 981 merged; starting a fresh one" <<<"$out" && ok "a fresh marker is said, and the launcher brings a session back" || bad "no fresh restart (rc=$rc)" "$out"
grep -q "^RUN2:" <<<"$out" && ! grep -q "^RUN2:.*--resume" <<<"$out" && ! grep -q "^RUN2:.*--continue" <<<"$out" && ok "…with no --resume and no --continue: a new conversation" || bad "fresh relaunch resumed" "$(grep RUN2 <<<"$out")"
grep -q "^RUN2:.*finished its job and started this one fresh: PR 981 merged" <<<"$out" && ok "…and the opening prompt carries the note" || bad "no note in the opening" "$(grep RUN2 <<<"$out")"
[[ ! -e "$STATE/agents/$LOGIN/restart.json" ]] && ok "…and the marker is consumed" || bad "fresh marker left behind"
# A launch with its own prompt would be relaunched with that prompt and
# no note: the finished job again. Not relaunched, and said.
rm -f "$SANDBOX/runs"
out="$(runa "do the job" 2>&1)"; rc=$?
grep -q "^RUN1:opening=0:" <<<"$out" && ok "a launch with its own prompt tells the session so" || bad "opening flag with a prompt" "$(grep RUN1 <<<"$out")"
[[ $rc -eq 143 ]] && ! grep -q "^RUN2:" <<<"$out" && grep -q "carried its own prompt; not relaunching" <<<"$out" && [[ ! -e "$STATE/agents/$LOGIN/restart.json" ]] \
    && ok "…and a fresh marker under it is not a relaunch of that prompt" || bad "prompt replayed (rc=$rc)" "$out"
write_fake_ori

echo "launch: a fresh session for a job starts in that job's working copy, with the job in its opening"
# fabric-fresh --job writes the job's id into the marker; the relaunch
# moves to the job's working copy when it is there and clean, and says
# the job in the opening prompt. Anything else starts where it was, and why.
fresh_job_session() {  # fresh_job_session <job id>
cat > "$SANDBOX/bin/ori" <<FAKE
#!/usr/bin/env bash
if [[ "\${1:-}" == auth ]]; then echo '{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}'; exit 0; fi
n="\$(cat "$SANDBOX/runs" 2>/dev/null || echo 0)"; echo \$((n+1)) > "$SANDBOX/runs"
if [[ "\$n" == 0 ]]; then
  printf '{"requested_at":"%s","piece":"a fresh session","status":"done","fresh":true,"note":"","job":"$1"}\\n' "\$(date -u -d '+2 seconds' +%Y-%m-%dT%H:%M:%SZ)" > "$STATE/agents/$LOGIN/restart.json"
  exit 143
fi
echo "RUN2:pwd=\$PWD:\$*"; exit 0
FAKE
chmod +x "$SANDBOX/bin/ori"; rm -f "$SANDBOX/runs"
}
jobs_cmd() { AGENT_FABRIC_ROOT="$FABRIC" AGENT_FABRIC_STATE_DIR="$STATE" python3 "$FABRIC/tools/fabric/jobs.py" "$@"; }
rm -rf "$SANDBOX/other"; mkdir -p "$SANDBOX/other"; git init -q "$SANDBOX/other"
jobs_cmd add "ship the other thing" --working-copy "$SANDBOX/other" --topic routing >/dev/null
jobs_cmd add "a job whose copy is gone" --working-copy "$SANDBOX/gone" >/dev/null
fresh_job_session j1
out="$(runa 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "^RUN2:pwd=$SANDBOX/other:" <<<"$out" && grep -q "starting job j1 in $SANDBOX/other" <<<"$out" \
  && ok "the relaunch starts in the job's working copy, and says so" || bad "not in the job's copy (rc=$rc)" "$out"
grep -q "^RUN2:.*It is for your job j1, ship the other thing ([^)]*topic routing): read it in full with fabric-jobs show j1" <<<"$out" \
  && ! grep -q "^RUN2:.*Then wait for instructions" <<<"$out" \
  && ok "…and the opening prompt carries the job in place of waiting for instructions" || bad "no job in the opening" "$(grep RUN2 <<<"$out")"
echo dirty > "$SANDBOX/other/f"
fresh_job_session j1
out="$(runa 2>&1)"; rc=$?
grep -q "^RUN2:pwd=$SANDBOX/repo:" <<<"$out" && grep -q "job j1's working copy $SANDBOX/other has uncommitted changes; starting in $SANDBOX/repo" <<<"$out" \
  && ok "a job's copy with uncommitted changes: the old directory, and why" || bad "dirty copy entered" "$out"
fresh_job_session j2
out="$(runa 2>&1)"; rc=$?
grep -q "^RUN2:pwd=$SANDBOX/repo:" <<<"$out" && grep -q "job j2's working copy $SANDBOX/gone is not there" <<<"$out" \
  && grep -q "^RUN2:.*It is for your job j2" <<<"$out" \
  && ok "a job's copy that is gone: the old directory, and why — the job is still said" || bad "missing copy" "$out"
write_fake_ori

echo "launch: a fabric checkout behind origin/main is pulled and the launcher re-executes on it"
# The fixture fabric becomes a git checkout with a bare origin one commit ahead.
mkfabric
G() { git -C "$FABRIC" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@"; }
G init -q -b main >/dev/null 2>&1; G add -A >/dev/null; G commit -q -m base >/dev/null
rm -rf "$SANDBOX/origin.git"; git init -q --bare -b main "$SANDBOX/origin.git"
G remote add origin "$SANDBOX/origin.git"; G push -q origin main 2>/dev/null
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && ok "current: the fetch finds nothing behind, launch proceeds" || bad "current checkout refused" "$out"
# origin gains a commit the checkout lacks
rm -rf "$SANDBOX/other"; git clone -q "$SANDBOX/origin.git" "$SANDBOX/other"
git -C "$SANDBOX/other" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q --allow-empty -m newer; git -C "$SANDBOX/other" push -q origin main
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "was 1 commit(s) behind origin/main; pulled to" <<<"$out" && grep -q "relaunching on it" <<<"$out" && ok "behind: pulled, said so, relaunched" || bad "stale checkout not pulled" "$out"
[[ "$(G rev-parse HEAD)" == "$(git -C "$SANDBOX/other" rev-parse HEAD)" ]] && ok "…the checkout is at origin/main" || bad "not pulled" "$(G log --oneline -2)"
grep -q "resolved profile" <<<"$out" && ok "…and the relaunch resolved the profile (one pull, one relaunch)" || bad "no profile after the relaunch" "$out"
# behind again, with a local commit that cannot fast-forward: refused with the reason
git -C "$SANDBOX/other" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q --allow-empty -m newer2; git -C "$SANDBOX/other" push -q origin main
G commit -q --allow-empty -m local-divergence
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && grep -q "cannot fast-forward" <<<"$out" && ! grep -q "resolved profile" <<<"$out" && ok "diverged: refused with the reason, before resolving anything" || bad "diverged checkout admitted" "$out"
G reset -q --hard origin/main
# behind, with the override: launches without pulling, loudly
git -C "$SANDBOX/other" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q --allow-empty -m newer3; git -C "$SANDBOX/other" push -q origin main
out="$(AGENT_FABRIC_ALLOW_STALE=1 run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "WARNING — agent-fabric is 1 commit(s) behind" <<<"$out" && [[ "$(G rev-parse HEAD)" != "$(git -C "$SANDBOX/other" rev-parse HEAD)" ]] && ok "AGENT_FABRIC_ALLOW_STALE=1: launches without pulling, loudly" || bad "override" "$out"
# a relaunch that is still behind does not loop
out="$(AGENT_FABRIC_PULLED=1 run --print 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && grep -q "still 1 commit(s) behind origin/main after a pull; not relaunching again" <<<"$out" && ok "a second relaunch is refused: no loop" || bad "loop guard" "$out"
G pull -q --ff-only origin main
G remote set-url origin /nonexistent/origin.git
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "could not fetch origin/main" <<<"$out" && ok "origin unreachable: launches on what is checked out, and says so" || bad "offline refused" "$out"

echo "launch: the working copy the session starts in is brought up to date, or its gap is said"
mkfabric
R() { git -C "$SANDBOX/repo" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "$@"; }
R symbolic-ref HEAD refs/heads/main; R commit -q --allow-empty -m base
rm -rf "$SANDBOX/wc-origin.git" "$SANDBOX/wc-other"; git init -q --bare -b main "$SANDBOX/wc-origin.git"
R remote add origin "$SANDBOX/wc-origin.git"; R push -q origin main 2>/dev/null
git clone -q "$SANDBOX/wc-origin.git" "$SANDBOX/wc-other"
wc_ahead() { git -C "$SANDBOX/wc-other" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q --allow-empty -m "$1"; git -C "$SANDBOX/wc-other" push -q origin main; }
wc_ahead newer
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "was 1 commit(s) behind origin/main; fast-forwarded to" <<<"$out" && [[ "$(R rev-parse HEAD)" == "$(git -C "$SANDBOX/wc-other" rev-parse HEAD)" ]] && ok "on a clean main: fast-forwarded before the session loads its CLAUDE.md" || bad "working copy not brought up to date" "$out"
wc_ahead newer2; R checkout -q -b feature
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "(feature) lacks 1 commit(s) of origin/main" <<<"$out" && [[ "$(R rev-parse HEAD)" != "$(git -C "$SANDBOX/wc-other" rev-parse HEAD)" ]] && ok "on another branch: the gap is said and nothing moves" || bad "a feature branch was touched or not reported" "$out"
R checkout -q main; echo change > "$SANDBOX/repo/tracked"; R add tracked
out="$(run --print 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "(main) lacks 1 commit(s) of origin/main" <<<"$out" && ! R diff --cached --quiet -- tracked && ok "on a main with staged changes: the gap is said and nothing moves" || bad "a dirty main was moved or not reported" "$out"
R reset -q --hard; R remote remove origin; rm -rf "$SANDBOX/wc-origin.git" "$SANDBOX/wc-other"

echo "launch: the role rides in the system prompt file"
mkfabric
out="$(run --version 2>&1)"; rc=$?
[[ -f "$STATE/agents/$LOGIN/launch-prompt.md" ]] && ok "the prompt file is written under the agent's state dir" || bad "no prompt file" "$(ls -la "$STATE/agents/$LOGIN" 2>&1)"
grep -q "FIXTURE-CHARTER-LINE" "$STATE/agents/$LOGIN/launch-prompt.md" && ok "…and carries the bound role's charter body" || bad "charter not in the prompt" "$(head -40 "$STATE/agents/$LOGIN/launch-prompt.md")"
grep -q "^You are agent \`$LOGIN\` on host" "$STATE/agents/$LOGIN/launch-prompt.md" && grep -q "the role \*\*backend-dev\*\*" "$STATE/agents/$LOGIN/launch-prompt.md" && ok "…the identity header names agent and role" || bad "header wrong" "$(head -5 "$STATE/agents/$LOGIN/launch-prompt.md")"
grep -q "No brief has been distilled" "$STATE/agents/$LOGIN/launch-prompt.md" && ok "…a missing brief is a placeholder, not a refusal" || bad "no placeholder" "$(grep -n brief "$STATE/agents/$LOGIN/launch-prompt.md")"
grep -q "REPLY-EXPECTED: yes" "$STATE/agents/$LOGIN/launch-prompt.md" && grep -q "memory/domains/backend-dev/" "$STATE/agents/$LOGIN/launch-prompt.md" && ok "…the team and memory sections are rendered for the role" || bad "shared sections missing" ""
! grep -q "class: charter" "$STATE/agents/$LOGIN/launch-prompt.md" && ok "…without frontmatter" || bad "frontmatter leaked" ""
digest="sha256:$(sha256sum "$STATE/agents/$LOGIN/launch-prompt.md" | cut -d' ' -f1)"
grep -q "ORI-ENV:AGENT_FABRIC_LAUNCH_ROLE=backend-dev$" <<<"$out" && ok "role stamped in the child env" || bad "no role stamp" "$out"
grep -q "ORI-ENV:AGENT_FABRIC_LAUNCH_PROMPT_DIGEST=$digest$" <<<"$out" && ok "the prompt's sha256 stamped, and it is the file's" || bad "digest stamp wrong" "$out"
mkfabric
out="$(run --print 2>&1)"
grep -q "export AGENT_FABRIC_LAUNCH_ROLE=backend-dev" <<<"$out" && grep -q "export AGENT_FABRIC_LAUNCH_PROMPT_DIGEST=sha256:" <<<"$out" && grep -q "prompt  : $STATE/agents/$LOGIN/launch-prompt.md (" <<<"$out" && ok "--print shows the role, the digest and the prompt path" || bad "--print hides the prompt" "$out"
! grep -q "EXECCED" <<<"$out" && ok "…and execs nothing" || bad "--print exec'd" "$out"
mkfabric; rm "$FABRIC/identities/roles/backend-dev/charter.md"
out="$(run --version 2>&1)"; rc=$?
[[ $rc -ne 0 ]] && grep -q "could not render the role's system prompt" <<<"$out" && ! grep -q "EXECCED" <<<"$out" && ok "a role with no charter cannot launch: refused before exec" || bad "launched without a charter" "$out"

echo "model-audit: provider values are allowlisted, never echoed by default"
out="$(env -i PATH="$PATH" HOME="$HOME" ANTHROPIC_CUSTOM_HEADERS='Authorization: Bearer test-secret' ANTHROPIC_BASE_URL='https://key-secret@proxy.example/api' ANTHROPIC_DEFAULT_OPUS_MODEL='anthropic/claude-opus-5' bash "$HERE/model-audit.sh" 2>&1)"
! grep -q 'test-secret' <<<"$out" && grep -q 'ANTHROPIC_CUSTOM_HEADERS = <set, ' <<<"$out" && ok "a non-allowlisted provider variable is reported set, not printed" || bad "credential printed in clear" "$out"
! grep -q 'key-secret' <<<"$out" && grep -q 'ANTHROPIC_BASE_URL = https://proxy.example$' <<<"$out" && ok "the base URL prints scheme+host, no userinfo" || bad "base URL userinfo leaked" "$out"
grep -q 'ANTHROPIC_DEFAULT_OPUS_MODEL = anthropic/claude-opus-5' <<<"$out" && ok "an allowlisted pin prints its value" || bad "pin redacted" "$out"
grep -q 'not launched via runtime/openrouter/launch' <<<"$out" && ok "no stamp: says the session model is not visible" || bad "guessed a session model" "$out"
out="$(env -i PATH="$PATH" HOME="$HOME" ANTHROPIC_BASE_URL='HTTPS://key@proxy.example:8443?api_key=qs-secret#frag-secret' bash "$HERE/model-audit.sh" 2>&1)"
! grep -qE 'key@|qs-secret|frag-secret' <<<"$out" && grep -q 'ANTHROPIC_BASE_URL = https://proxy.example:8443$' <<<"$out" && ok "uppercase scheme, no path, query+fragment: scheme://host:port only" || bad "base URL leaked" "$out"
out="$(env -i PATH="$PATH" HOME="$HOME" ANTHROPIC_BASE_URL='sk-or-v1-notaurl' bash "$HERE/model-audit.sh" 2>&1)"
! grep -q 'sk-or' <<<"$out" && grep -q 'ANTHROPIC_BASE_URL = <set, 16 chars>' <<<"$out" && ok "a non-URL base value is reported set, never echoed" || bad "non-URL printed" "$out"
out="$(env -i PATH="$PATH" HOME="$HOME" AGENT_FABRIC_LAUNCH_SESSION_MODEL=vendor/s AGENT_FABRIC_LAUNCH_PROFILE=r/a AGENT_FABRIC_LAUNCH_AGENT=a bash "$HERE/model-audit.sh" 2>&1)"
grep -q 'session : vendor/s' <<<"$out" && grep -q 'profile : r/a' <<<"$out" && grep -q 'agent   : a' <<<"$out" && ok "the launcher's stamp is reported, agent included" || bad "stamp not reported" "$out"
out="$(env -i PATH="$PATH" HOME="$HOME" ANTHROPIC_CUSTOM_HEADERS=$'Authorization: Bearer first-secret\nANTHROPIC_MODEL=second-secret' bash "$HERE/model-audit.sh" 2>&1)"
! grep -qE 'first-secret|second-secret' <<<"$out" && grep -q 'ANTHROPIC_CUSTOM_HEADERS = <set, 64 chars>' <<<"$out" && ! grep -q 'ANTHROPIC_MODEL = ' <<<"$out" && ok "a newline inside a redacted value neither splits the entry nor truncates the count" || bad "env entry boundary lost on newline" "$out"
out="$(env -i PATH="$PATH" HOME="$HOME" ANTHROPIC_BASE_URL='HTTPS://OPENROUTER.AI/api' bash "$HERE/model-audit.sh" 2>&1)"
grep -q 'routed through OpenRouter' <<<"$out" && ok "an uppercase openrouter.ai host classifies as OpenRouter" || bad "host test is case-sensitive" "$out"
out="$(env -i PATH="$PATH" HOME="$HOME" ANTHROPIC_BASE_URL='https://notopenrouter.example/openrouter' bash "$HERE/model-audit.sh" 2>&1)"
grep -q 'does not name OpenRouter' <<<"$out" && ok "a look-alike host with openrouter in the path is not OpenRouter" || bad "host test is a substring match" "$out"

echo
if [[ $FAIL -eq 0 ]]; then
    echo "test_launch: OK — $PASS assertion(s) passed."
else
    echo "test_launch: FAILED — $FAIL assertion(s) failed."; exit 1
fi
