#!/usr/bin/env bash
# runtime/provisioning/secrets/enroll.sh — put an identity's secrets in
# Doppler and hand the account its read-only token. Run by the
# fabric-coordinator (root via sudo; the coordinator's Doppler CLI token
# is the admin credential).
#
#   enroll.sh <login>...      enrol these accounts
#   enroll.sh --all           every account with a ~/projects/agent-fabric
#   enroll.sh sync-all        `fabric-secrets sync` as every enrolled account
#                             (after a rotation in the dashboard)
#   enroll.sh fill-from <login> [<target>...]
#                             copy into each target config (default: every
#                             enrolled login) the names it lacks and <login>'s
#                             config has — never a name already present,
#                             never the identity names, never the
#                             coordinator's own credentials (*_ADMIN_KEY,
#                             *_PROVISIONING_KEY, AGENT_FABRIC_READ_TOKEN),
#                             never a per-login name from the registry's
#                             agent_env (a port offset, OPENAI_API_KEY —
#                             those have their own steps); then sync the
#                             targets. Values stay inside
#                             doppler calls, never on a terminal.
#   enroll.sh issue-openrouter-keys <login>...
#                             give each login an OpenRouter API key of its
#                             own (named after the login, as the existing
#                             keys are) and set it in its
#                             config, replacing a shared one; needs the
#                             coordinator's OpenRouter PROVISIONING key in
#                             the coordinator's own Doppler config as
#                             OPENROUTER_PROVISIONING_KEY (dashboard →
#                             Settings → Provisioning Keys). Key values
#                             go API → doppler, never through a terminal.
#   enroll.sh issue-openai-keys <login>...
#                             give each login an OpenAI API key of its own:
#                             a service account agent-fabric-<login> in
#                             the organisation's project (the only way to
#                             mint a project key programmatically; the key
#                             is returned once), set as OPENAI_API_KEY in
#                             its config. Needs the coordinator's OpenAI
#                             ADMIN key in the coordinator's own config as
#                             OPENAI_ADMIN_KEY (dashboard -> Organization ->
#                             Admin keys) and, with several projects,
#                             OPENAI_PROJECT_ID there too. The Usage API
#                             then reports per api_key_id.
#   enroll.sh set-shared <NAME> <file>
#                             set NAME in EVERY enrolled config to the value
#                             read from <file> (a rotation of a shared
#                             secret such as CLAUDE_BRIDGE_AUTH_TOKEN), then
#                             sync every account. The file is shredded.
#   enroll.sh --dry-run ...   say what would happen; touch nothing
#
# Per login, in order — each step idempotent, none prints a value:
#   1. install the doppler CLI system-wide (once)
#   2. branch config `<env>_<login>` under environment `agents` in project
#      agent-fabric — `agents2`, `agents3`, `agents4` once one holds its ten
#      configs (the Developer plan: four environments of ten configs, so
#      the login is the branch config, never the environment); the name is
#      recorded in the account's doppler config at scope / (enclave.config)
#      so fabric-secrets knows which config is its own
#   3. MIGRATE what the account holds today into that config, gathered as
#      the account into a 0600 temp file that is uploaded and shredded:
#        OPENROUTER_API_KEY        `export` line in ~/.bashrc, or the
#                                  secrets.env of an earlier sync
#        GH_TOKEN                  `gh auth token`
#        CLAUDE_BRIDGE_AUTH_TOKEN  env.* in <clone>/.claude/settings.local.json;
#                                  for the relay host, the runtime dir's bridge-token
#        GIT_*                     git config --global (name, email, signingkey,
#                                  gpg.program) — from the template when unset
#        SSH_PRIVATE_KEY/PUBLIC    ~/.ssh/id_ed25519(.pub)
#        AGENT_LOGIN, AGENT_HOST   the login, this host
#      A name already in Doppler is NOT overwritten (Doppler is the record
#      once enrolled; --remigrate forces the upload).
#   4. a read-only service token on that config, piped straight into the
#      account's ~/.doppler/.doppler.yaml (`doppler configure set token`)
#   5. `fabric-secrets sync` as the account, then verify: ori sees the key
#      from the environment, gh sees GH_TOKEN, git has the signing key
#   6. only after 5: retire the old sources — the ~/.bashrc export line, the
#      settings.local.json entries, the gh hosts.yml login. The synced env
#      file is the one source from here.
#
# Under failure (test_enroll.sh injects each, against a fake doppler): a
# stop at any step leaves the old sources in place and nothing under $TMP;
# a re-run converges — the config it created is reused, names already in
# Doppler are not re-uploaded, a token issued but never stored is noticed
# and another issued; an OpenRouter key minted before a failed Doppler
# write is deleted again. OPENROUTER_API_BASE points the keys API at a
# test server.
#
# WHERE IT RUNS (review, 2026-09-16). This script is the coordinator's:
# Doppler, the service tokens and the API keys never leave it. Everything
# that touches an account's host — its home, its ~/.doppler, the sync,
# the retirement of old sources — goes through runtime/hostexec/hostexec
# to enroll-worker.sh on the host the account is placed on
# (runtime/hosts/registry.json; --host <id> for a login not placed yet),
# directly on this host or over ssh. AGENT_HOST is what that host says of
# itself, never what this one assumes.
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../.." && pwd)"
PROJECT="${AGENT_FABRIC_SECRETS_PROJECT:-agent-fabric}"
HOSTS="${AGENT_FABRIC_HOSTS_REGISTRY:-$ROOT/runtime/hosts/registry.json}"
HX="$ROOT/runtime/hostexec/hostexec"
# Every Doppler call is bounded: a token kept in a locked desktop keyring
# makes doppler wait forever (fabric-secrets bounds its own the same way).
DOPPLER_TIMEOUT_S="${AGENT_FABRIC_DOPPLER_TIMEOUT_S:-30}"
doppler() { timeout "$DOPPLER_TIMEOUT_S" doppler "$@"; }   # timeout execs the binary on PATH, not this function
ENVIRONMENT="${AGENT_FABRIC_SECRETS_ENVIRONMENT:-agents}"
DOPPLER_BIN="${DOPPLER_BIN:-/usr/local/bin/doppler}"
TEMPLATE="${AGENT_FABRIC_SECRETS_TEMPLATE:-$HOME/.config/agent-fabric/identity-template.env}"
SUDO="${SUDO:-sudo}"

DRY=0; REMIGRATE=0; MODE=enrol; LOGINS=(); HOST_FLAG=""
while (( $# )); do
  a="$1"; shift
  case "$a" in
    --host) HOST_FLAG="$1"; shift; continue ;;
    --host=*) HOST_FLAG="${a#--host=}"; continue ;;
    --dry-run) DRY=1 ;;
    --remigrate) REMIGRATE=1 ;;
    --all) MODE=all ;;
    sync-all) MODE=sync-all ;;
    fill-from) MODE=fill-from ;;
    set-shared) MODE=set-shared ;;
    issue-openrouter-keys) MODE=issue-openrouter-keys ;;
    issue-openai-keys) MODE=issue-openai-keys ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    -*) echo "enroll: unknown flag $a" >&2; exit 2 ;;
    *) LOGINS+=("$a") ;;
  esac
done

# Progress goes to stderr: several steps run inside $(...) captures.
say() { printf 'enroll: %s\n' "$*" >&2; }
die() { printf 'enroll: %s\n' "$*" >&2; exit 1; }
run() { if (( DRY )); then say "would: $*"; else "$@"; fi; }
# The host an account lives on: --host, else its placement in the
# registry, else this host. The coordinator's own login is always here.
host_of() {
  local login="$1"
  if [[ "$login" == "$(id -un)" ]]; then echo "$LOCAL_HOST"; return; fi
  if [[ -n "$HOST_FLAG" ]]; then echo "$HOST_FLAG"; return; fi
  local placed; placed="$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print((r.get("placement") or {}).get(sys.argv[2], ""))' "$HOSTS" "$login")"
  echo "${placed:-$LOCAL_HOST}"
}
LOCAL_HOST="$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print(next((h for h,e in (r.get("hosts") or {}).items() if e.get("ssh") is None), ""))' "$HOSTS")"
[[ -n "$LOCAL_HOST" ]] || die "runtime/hosts/registry.json names no local host (ssh null)"
# As the account, on its host, from its home (the coordinator's cwd is not
# readable to it, and git stats the cwd even for --global). The
# coordinator's own login runs directly — its gh credential sits in the
# session keyring, which a sudo'd shell cannot open. stdin flows through:
# a token piped in is never an argument.
as_login() {
  local login="$1"; shift
  if [[ "$login" == "$(id -un)" ]]; then "$ROOT/runtime/hostexec/worker" -- "$@"; return; fi
  "$HX" "$(host_of "$login")" --as "$login" -- "$@"
}
# As the host's operator (sudo there), for what the account cannot do to itself.
as_operator() { local login="$1"; shift; "$HX" "$(host_of "$login")" -- "$@"; }
# The account's own checkout of the fabric, relative to ITS home (the
# worker starts there): the coordinator's is not readable to it.
FABRIC_SECRETS_REL="projects/agent-fabric/runtime/provisioning/secrets/fabric-secrets"
fabric_secrets_of() {
  if [[ "$1" == "$(id -un)" ]]; then echo "$ROOT/runtime/provisioning/secrets/fabric-secrets"; else echo "$FABRIC_SECRETS_REL"; fi
}
ENROLL_WORKER="@fabric/runtime/provisioning/secrets/enroll-worker.sh"

all_logins() {
  # The accounts the fabric knows: the registry's placements, whichever host.
  python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("\n".join(sorted((r.get("placement") or {}))))' "$HOSTS"
}

# ---- 1. the CLI, once -----------------------------------------------------
install_cli() {
  if [[ -x "$DOPPLER_BIN" ]]; then return 0; fi
  local src; src="$(command -v doppler || true)"
  [[ -n "$src" ]] || die "no doppler CLI to install from (command -v doppler)"
  say "installing $src -> $DOPPLER_BIN"
  run $SUDO install -m 755 "$src" "$DOPPLER_BIN"
}

# ---- 2. the config -------------------------------------------------------
existing_config() {  # the config already holding this login, if any
  doppler configs --project "$PROJECT" --json 2>/dev/null | python3 -c '
import json, sys
login = sys.argv[1]
for c in (json.load(sys.stdin) or []):
    if c.get("name", "").endswith("_" + login) and not c.get("root"): print(c["name"]); break' "$1"
}
ensure_config() {
  local login="$1" name; name="$(existing_config "$login")"
  if [[ -n "$name" ]]; then echo "$name"; return 0; fi
  if (( DRY )); then say "would: create branch config ${ENVIRONMENT}_$login (or the next environment's) in $PROJECT"; echo "${ENVIRONMENT}_$login"; return 0; fi
  local env
  for env in "$ENVIRONMENT" "${ENVIRONMENT}2" "${ENVIRONMENT}3" "${ENVIRONMENT}4"; do
    doppler environments get "$env" --project "$PROJECT" >/dev/null 2>&1 \
      || doppler environments create "$env" "$env" --project "$PROJECT" >/dev/null 2>"$TMP/env.err" \
      || die "cannot create environment $env: $(tail -1 "$TMP/env.err")"
    name="${env}_$login"
    if doppler configs create --name "$name" --environment "$env" --project "$PROJECT" >/dev/null 2>"$TMP/cfg.err"; then
      say "created branch config $name"; echo "$name"; return 0
    fi
    grep -q "limit of .* configs" "$TMP/cfg.err" || die "cannot create config $name: $(tail -1 "$TMP/cfg.err")"
    say "environment $env is full; trying the next"
  done
  die "every environment is full; the plan allows four of ten configs"
}
record_config() {  # tell the account which config is its own
  local login="$1" config="$2"
  if (( DRY )); then say "would: record enclave.config=$config for $login"; return 0; fi
  as_login "$login" bash -c 'mkdir -p -m 700 ~/.doppler; doppler configure set "enclave.project=$1" "enclave.config=$2" --scope / --silent' -- "$PROJECT" "$config" \
    || die "$login: could not record the config name"
}

# ---- 3. migrate ----------------------------------------------------------
# Gathers as the account; writes NAME=value lines into $out (0600, owned by
# root). Values never pass through this shell's stdout.
gather() {
  local login="$1" out="$2"
  # The template (git identity strings) is the coordinator's file; its
  # lines travel to the account's worker as arguments, never as a path.
  # AGENT_HOST comes back from the worker: the host names itself.
  local -a tpl=()
  [[ -r "$TEMPLATE" ]] && mapfile -t tpl < <(grep -E '^[A-Z_]+=' "$TEMPLATE")
  as_login "$login" "$ENROLL_WORKER" gather "$login" "${tpl[@]}" > "$out"
}

migrate() {
  local login="$1" config="$2"
  local gathered="$TMP/$login.json"
  ( umask 077; : > "$gathered" )
  gather "$login" "$gathered" || die "$login: gathering failed"
  local have=""
  have="$(doppler secrets --only-names --json --project "$PROJECT" --config "$config" 2>/dev/null | python3 -c '
import json, sys
try: print(" ".join(json.load(sys.stdin).keys()))
except ValueError: pass' || true)"
  # Names already in Doppler stay unless --remigrate: once enrolled, Doppler is the record.
  local upload="$TMP/$login.upload.json"
  ( umask 077; : > "$upload" )
  # The GZCoord token is one shared secret: an account that never held a
  # copy (no clone yet) gets the relay host's, read here as the coordinator.
  local shared_bridge="${AGENT_FABRIC_RELAY_TOKEN_FILE:-$(dirname "$ROOT")/.gzcoord/bridge-token}"
  python3 - "$gathered" "$upload" "$have" "$REMIGRATE" "$shared_bridge" <<'PY'
import json, sys
src, dst, have, force, bridge = sys.argv[1], sys.argv[2], set(sys.argv[3].split()), sys.argv[4] == "1", sys.argv[5]
vals = json.load(open(src))
if "CLAUDE_BRIDGE_AUTH_TOKEN" not in vals:
    try: vals["CLAUDE_BRIDGE_AUTH_TOKEN"] = open(bridge).read().strip()
    except OSError: pass
keep = {k: v for k, v in vals.items() if force or k not in have}
json.dump(keep, open(dst, "w"))
print("gathered: " + ", ".join(sorted(vals)))
print("upload:   " + (", ".join(sorted(keep)) or "(nothing new)"))
PY
  if [[ "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$upload")" != "0" ]]; then
    # upload echoes what it set; nothing of that reaches the terminal.
    run doppler secrets upload "$upload" --project "$PROJECT" --config "$config" --silent >/dev/null || die "$login: upload failed"
  fi
  shred -u "$gathered" "$upload" 2>/dev/null || rm -f "$gathered" "$upload"
}

# ---- 4. the account's token ---------------------------------------------
issue_token() {
  local login="$1" config="$2"
  local name="$(host_of "$login")/$login"
  # The coordinator's own login reads its config with the CLI token it
  # already holds (workplace admin); a service token at scope / would
  # replace that credential and lock the coordinator out of the project.
  if [[ "$login" == "$(id -un)" ]]; then say "$login: coordinator keeps its CLI token; no service token"; return 0; fi
  # Issued before AND held by the account: done. Issued but not held (the
  # store step failed last time, or the account's ~/.doppler was rebuilt)
  # is the partially-enrolled state — a second token of the same name is
  # issued and the unused one named for revoking; the account is never
  # left with a record that says "done" and no credential.
  if doppler configs tokens --project "$PROJECT" --config "$config" --json 2>/dev/null | python3 -c '
import json, sys
try: sys.exit(0 if any(t.get("name") == sys.argv[1] for t in (json.load(sys.stdin) or [])) else 1)
except ValueError: sys.exit(1)' "$name"; then
    if [[ -n "$(as_login "$login" timeout "$DOPPLER_TIMEOUT_S" doppler configure get token --plain --scope / 2>/dev/null)" ]]; then
      say "$login: service token $name already issued; keeping the account's copy"
      return 0
    fi
    (( DRY )) || say "$login: a token named $name exists but the account holds none (an earlier run stopped between issuing and storing); issuing another — revoke the unused one in the dashboard"
  fi
  if (( DRY )); then say "would: issue read token $name and configure it for $login"; return 0; fi
  # The token goes from doppler's stdout into the account's config file and nowhere else.
  doppler configs tokens create "$name" --project "$PROJECT" --config "$config" --access read --plain \
    | as_login "$login" bash -c 'read -r t; [ -n "$t" ] || exit 1; mkdir -p -m 700 ~/.doppler; doppler configure set token "$t" --scope / --silent' \
    || die "$login: could not issue or store the service token"
  say "$login: service token $name issued and stored"
}

# ---- 5. sync + verify ----------------------------------------------------
sync_and_verify() {
  local login="$1"
  if (( DRY )); then say "would: fabric-secrets sync as $login and verify"; return 0; fi
  as_login "$login" "$(fabric_secrets_of "$login")" sync || say "$login: sync reported missing names (see above)"
  local ok=1
  # A login shell, for the account's own profile — with the PATH the
  # worker set restored inside it (Debian's /etc/profile assigns PATH
  # outright; the worker passes its PATH as AGENT_FABRIC_PATH for this).
  if as_login "$login" bash -lc 'export PATH="${AGENT_FABRIC_PATH:-$HOME/.local/bin}:$PATH"; ori auth --json' 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin); d = d.get("data", d)
    sys.exit(0 if d.get("authenticated") is True and (d.get("source") or {}).get("kind") == "environment" else 1)
except (ValueError, AttributeError): sys.exit(1)'; then
    say "$login: ori authenticated from the environment"
  else
    say "$login: ori NOT authenticated from the environment (no OPENROUTER_API_KEY in Doppler?)"; ok=0
  fi
  if as_login "$login" bash -lc 'export PATH="${AGENT_FABRIC_PATH:-$HOME/.local/bin}:$PATH"; gh auth status' >/dev/null 2>&1; then say "$login: gh authenticated"; else say "$login: gh NOT authenticated"; ok=0; fi
  if [[ -n "$(as_login "$login" git config --global --get user.signingkey)" ]]; then say "$login: signing key set"; else say "$login: signing key NOT set"; ok=0; fi
  return $(( ok ? 0 : 1 ))
}

# ---- 6. retire the old sources -------------------------------------------
retire_old_sources() {
  local login="$1"
  if (( DRY )); then say "would: retire .bashrc export, settings.local.json entries and gh hosts.yml login for $login"; return 0; fi
  # Not the gh keyring login for the coordinator's own account: it is the
  # session's live credential, and the exported token only reaches new
  # shells — the worker skips it when the login is the operator's own.
  local keep=(); [[ "$login" == "$(id -un)" ]] && keep=(keep-gh)
  as_login "$login" "$ENROLL_WORKER" retire "$login" "${keep[@]}"
}

enrol() {
  local login="$1"
  say "== $login on $(host_of "$login")"
  # The account exists there, has its fabric checkout, owns ~/.config —
  # the host's operator answers, and refuses otherwise.
  as_operator "$login" "$ENROLL_WORKER" prepare-home "$login" >/dev/null || die "$login: not ready on $(host_of "$login") (above)"
  local config; config="$(ensure_config "$login")" || exit 1
  migrate "$login" "$config"
  issue_token "$login" "$config"
  record_config "$login" "$config"
  if sync_and_verify "$login"; then
    retire_old_sources "$login"
  else
    say "$login: verification incomplete; old sources kept — fix the Doppler config, then re-run"
  fi
}

# ---- fill-from: complete configs from another login's ---------------------
config_of() {  # the config holding this login (recorded by enrol), or empty
  existing_config "$1"
}
fill_from() {
  local source="$1"; shift
  local src_cfg; src_cfg="$(config_of "$source")"
  [[ -n "$src_cfg" ]] || die "no config for $source"
  local targets=("$@")
  (( ${#targets[@]} )) || mapfile -t targets < <(all_logins | grep -vx "$source")
  local login tgt_cfg have missing
  for login in "${targets[@]}"; do
    [[ "$login" == "$source" ]] && continue
    tgt_cfg="$(config_of "$login")"
    [[ -n "$tgt_cfg" ]] || { say "$login: not enrolled, skipped"; continue; }
    have="$(doppler secrets --only-names --json --project "$PROJECT" --config "$tgt_cfg" 2>/dev/null | python3 -c '
import json, sys
try: print(" ".join(json.load(sys.stdin).keys()))
except ValueError: pass')"
    # Names the source has and the target lacks. Never copied: the identity
    # names; the coordinator's own credentials — the provisioning and admin
    # keys the issue-* commands use, and the fabric's read token — which the
    # source config holds precisely because it is the coordinator's (copying
    # them handed a fresh agent account the power to mint keys for every
    # other: brand-comms-01, 2026-09-15, deleted the same hour); and every
    # name projects/registry.json declares under `agent_env`, which is
    # per login by definition (a port offset, an OpenAI key of its own) and
    # is set by its own step, never inherited from another account.
    per_login="$(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
names = set(d.get("agent_env") or {})
for p in (d.get("projects") or {}).values(): names |= set(p.get("agent_env") or {})
print(" ".join(sorted(names)))' "$ROOT/projects/registry.json" 2>/dev/null)"
    missing="$(doppler secrets --only-names --json --project "$PROJECT" --config "$src_cfg" 2>/dev/null | python3 -c '
import json, sys
have = set(sys.argv[1].split())
skip = {"AGENT_LOGIN", "AGENT_HOST"} | set(sys.argv[2].split())
coordinator_only = ("_ADMIN_KEY", "_PROVISIONING_KEY", "AGENT_FABRIC_READ_TOKEN")
try: names = [n for n in json.load(sys.stdin) if not n.startswith("DOPPLER_") and n not in skip and n not in have
              and not any(n.endswith(c) or n == c for c in coordinator_only)]
except ValueError: names = []
print(" ".join(sorted(names)))' "$have" "$per_login")"
    if [[ -z "$missing" ]]; then say "$login: nothing missing"; continue; fi
    if (( DRY )); then say "would: copy $missing from $src_cfg into $tgt_cfg"; continue; fi
    local upload="$TMP/$login.fill.json"; ( umask 077; : > "$upload" )
    doppler secrets download --no-file --format json --project "$PROJECT" --config "$src_cfg" 2>/dev/null | python3 -c '
import json, sys
names = sys.argv[1].split(); out = sys.argv[2]
vals = json.load(sys.stdin)
json.dump({n: vals[n] for n in names if n in vals}, open(out, "w"))' "$missing" "$upload" || die "$login: could not read $src_cfg"
    doppler secrets upload "$upload" --project "$PROJECT" --config "$tgt_cfg" --silent >/dev/null || die "$login: upload failed"
    shred -u "$upload" 2>/dev/null || rm -f "$upload"
    say "$login: copied $missing from $source"
    as_login "$login" "$(fabric_secrets_of "$login")" sync --quiet || true
  done
}

# ---- issue-openai-keys: one service-account key per agent ----------------
issue_openai_keys() {
  local me_cfg; me_cfg="$(config_of "$(id -un)")"
  [[ -n "$me_cfg" ]] || die "no config for $(id -un)"
  local login tgt_cfg
  for login in "$@"; do
    tgt_cfg="$(config_of "$login")"
    [[ -n "$tgt_cfg" ]] || { say "$login: not enrolled, skipped"; continue; }
    if (( DRY )); then say "would: create OpenAI service account agent-fabric-$login and set OPENAI_API_KEY in $tgt_cfg"; continue; fi
    local upload="$TMP/$login.oaikey.json"; ( umask 077; : > "$upload" )
    python3 - "$PROJECT" "$me_cfg" "$login" "$upload" <<'PY' || die "$login: key creation failed"
import json, subprocess, sys, urllib.request
project, me_cfg, login, out = sys.argv[1:5]
def secret(name):
    r = subprocess.run(["doppler", "secrets", "get", name, "--plain", "--project", project, "--config", me_cfg], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""
adm = secret("OPENAI_ADMIN_KEY")
if not adm: print("enroll: OPENAI_ADMIN_KEY is not in the coordinator's config", file=sys.stderr); sys.exit(1)
H = {"Authorization": f"Bearer {adm}", "Content-Type": "application/json"}
def call(path, data=None):
    req = urllib.request.Request("https://api.openai.com/v1/" + path, data=json.dumps(data).encode() if data is not None else None, headers=H)
    try:
        with urllib.request.urlopen(req) as resp: return json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"enroll: OpenAI refused ({e.code}) on {path}: {e.read()[:160].decode(errors='replace')}", file=sys.stderr); sys.exit(1)
pid = secret("OPENAI_PROJECT_ID")
if not pid:
    projs = [p for p in call("organization/projects?limit=50")["data"] if p.get("status") == "active"]
    if len(projs) != 1:
        print(f"enroll: {len(projs)} active projects; set OPENAI_PROJECT_ID in the coordinator's config", file=sys.stderr); sys.exit(1)
    pid = projs[0]["id"]
# Named for what it is: this control plane's key for that login. A key is
# returned only at creation, so an account already there under this name
# (or the bare login, an earlier spelling) is replaced, never reused.
name = f"agent-fabric-{login}"
existing = {s["name"]: s["id"] for s in call(f"organization/projects/{pid}/service_accounts?limit=100")["data"]}
for old in (name, login):
    if old in existing:
        req = urllib.request.Request(f"https://api.openai.com/v1/organization/projects/{pid}/service_accounts/{existing[old]}", headers=H, method="DELETE")
        urllib.request.urlopen(req).read()
        print(f"enroll: {login}: replaced the existing service account {old}", file=sys.stderr)
sa = call(f"organization/projects/{pid}/service_accounts", {"name": name})
key = (sa.get("api_key") or {}).get("value")
if not key: print("enroll: OpenAI returned no key with the service account", file=sys.stderr); sys.exit(1)
json.dump({"OPENAI_API_KEY": key}, open(out, "w"))
print(f"enroll: created OpenAI service account {name} (key id {(sa.get('api_key') or {}).get('id', '?')})", file=sys.stderr)
PY
    doppler secrets upload "$upload" --project "$PROJECT" --config "$tgt_cfg" --silent >/dev/null || die "$login: upload failed"
    shred -u "$upload" 2>/dev/null || rm -f "$upload"
    say "$login: OPENAI_API_KEY set in $tgt_cfg"
    as_login "$login" "$(fabric_secrets_of "$login")" sync --quiet || true
  done
}

# ---- set-shared: one value into every config (a rotation) ----------------
set_shared() {
  local name="$1" file="$2"
  [[ "$name" =~ ^[A-Z][A-Z0-9_]*$ ]] || die "not a secret name: $name"
  [[ -r "$file" ]] || die "cannot read $file"
  local upload="$TMP/shared.json"; ( umask 077; : > "$upload" )
  python3 -c 'import json,sys; v=open(sys.argv[2]).read().strip(); assert v, "empty value"; json.dump({sys.argv[1]: v}, open(sys.argv[3], "w"))' "$name" "$file" "$upload" || die "could not read the value"
  local login cfg n=0
  for login in $(all_logins); do
    cfg="$(config_of "$login")"; [[ -n "$cfg" ]] || { say "$login: not enrolled, skipped"; continue; }
    if (( DRY )); then say "would: set $name in $cfg"; continue; fi
    doppler secrets upload "$upload" --project "$PROJECT" --config "$cfg" --silent >/dev/null || die "$login: upload failed"
    n=$((n+1))
  done
  shred -u "$upload" "$file" 2>/dev/null || rm -f "$upload" "$file"
  say "$name set in $n config(s); syncing every account"
  (( DRY )) || for login in $(all_logins); do as_login "$login" "$(fabric_secrets_of "$login")" sync --quiet || say "$login: sync reported a problem"; done
}

# ---- issue-openrouter-keys: one key per agent -----------------------------
# Per-agent spend follows the key (runtime/openrouter/launch): an account
# that runs on a copied key spends on someone else's. The provisioning key
# is read from the coordinator's config inside python and used there only.
issue_openrouter_keys() {
  local me_cfg; me_cfg="$(config_of "$(id -un)")"
  [[ -n "$me_cfg" ]] || die "no config for $(id -un)"
  local login tgt_cfg
  for login in "$@"; do
    tgt_cfg="$(config_of "$login")"
    [[ -n "$tgt_cfg" ]] || { say "$login: not enrolled, skipped"; continue; }
    if (( DRY )); then say "would: create OpenRouter key $login and set OPENROUTER_API_KEY in $tgt_cfg"; continue; fi
    local upload="$TMP/$login.orkey.json"; ( umask 077; : > "$upload" )
    # The key's hash (its handle at OpenRouter, not the secret) is kept
    # beside the upload so a failed store can delete the key it minted:
    # otherwise a key exists under the login's name that nothing records,
    # and the re-run mints a second (review, 2026-09-16).
    local hashf="$TMP/$login.orkey.hash"; ( umask 077; : > "$hashf" )
    python3 - "$PROJECT" "$me_cfg" "$login" "$upload" "$hashf" "${OPENROUTER_API_BASE:-https://openrouter.ai/api/v1}" <<'PY' || die "$login: key creation failed"
import json, subprocess, sys, urllib.request
project, me_cfg, name, out, hashf, base = sys.argv[1:7]
r = subprocess.run(["doppler", "secrets", "get", "OPENROUTER_PROVISIONING_KEY", "--plain",
                    "--project", project, "--config", me_cfg], capture_output=True, text=True)
prov = r.stdout.strip()
if r.returncode != 0 or not prov:
    print("enroll: OPENROUTER_PROVISIONING_KEY is not in the coordinator's config", file=sys.stderr); sys.exit(1)
req = urllib.request.Request(base + "/keys", data=json.dumps({"name": name}).encode(),
                             headers={"Authorization": f"Bearer {prov}", "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req) as resp: body = json.load(resp)
except urllib.error.HTTPError as e:
    print(f"enroll: OpenRouter refused ({e.code}): {e.read()[:200].decode(errors='replace')}", file=sys.stderr); sys.exit(1)
key = body.get("key") or (body.get("data") or {}).get("key")
if not key:
    print("enroll: OpenRouter returned no key", file=sys.stderr); sys.exit(1)
json.dump({"OPENROUTER_API_KEY": key}, open(out, "w"))
h = (body.get("data") or {}).get("hash") or ""
open(hashf, "w").write(h)
print(f"enroll: created OpenRouter key {name} (hash {h[:12]}…)", file=sys.stderr)
PY
    if ! doppler secrets upload "$upload" --project "$PROJECT" --config "$tgt_cfg" --silent >/dev/null; then
      shred -u "$upload" 2>/dev/null || rm -f "$upload"
      if python3 - "$PROJECT" "$me_cfg" "$hashf" "${OPENROUTER_API_BASE:-https://openrouter.ai/api/v1}" <<'PY'
import subprocess, sys, urllib.request
project, me_cfg, hashf, base = sys.argv[1:5]
h = open(hashf).read().strip()
if not h: sys.exit(1)
prov = subprocess.run(["doppler", "secrets", "get", "OPENROUTER_PROVISIONING_KEY", "--plain", "--project", project, "--config", me_cfg],
                      capture_output=True, text=True).stdout.strip()
req = urllib.request.Request(base + "/keys/" + h, method="DELETE", headers={"Authorization": f"Bearer {prov}"})
try:
    with urllib.request.urlopen(req): pass
except Exception: sys.exit(1)
PY
      then die "$login: Doppler upload failed; the key just minted was deleted at OpenRouter — nothing to clean up, re-run"
      else die "$login: Doppler upload failed AND the minted key could not be deleted: a key named $login exists at OpenRouter that nothing records — delete it in the dashboard, then re-run"
      fi
    fi
    shred -u "$upload" "$hashf" 2>/dev/null || rm -f "$upload" "$hashf"
    say "$login: OPENROUTER_API_KEY set in $tgt_cfg"
    as_login "$login" "$(fabric_secrets_of "$login")" sync --quiet || true
  done
}

# Every gathered value lives only under $TMP (0700) between gather and
# upload, and the EXIT trap removes it on any end — a die, a kill, a full
# disk (runtime/provisioning/secrets/test_enroll.sh injects each). A
# temporary directory that cannot be made is the stop, before anything
# is created remotely.
TMP="$(mktemp -d 2>/dev/null)" && [[ -d "$TMP" ]] || die "cannot create a temporary directory under ${TMPDIR:-/tmp} (full, or not writable): nothing done"
chmod 700 "$TMP" || die "cannot secure $TMP: nothing done"
trap 'rm -rf "$TMP"' EXIT
command -v doppler >/dev/null || die "doppler CLI not on PATH"
doppler projects get "$PROJECT" --json >/dev/null 2>&1 || die "Doppler project $PROJECT not reachable with this token"

case "$MODE" in
  fill-from)
    (( ${#LOGINS[@]} )) || die "fill-from needs the source login"
    fill_from "${LOGINS[@]}" ;;
  issue-openrouter-keys)
    (( ${#LOGINS[@]} )) || die "issue-openrouter-keys needs the logins"
    issue_openrouter_keys "${LOGINS[@]}" ;;
  issue-openai-keys)
    (( ${#LOGINS[@]} )) || die "issue-openai-keys needs the logins"
    issue_openai_keys "${LOGINS[@]}" ;;
  set-shared)
    (( ${#LOGINS[@]} == 2 )) || die "set-shared needs <NAME> <file>"
    set_shared "${LOGINS[0]}" "${LOGINS[1]}" ;;
  sync-all)
    for login in $(all_logins); do
      say "== $login"; as_login "$login" "$(fabric_secrets_of "$login")" sync || true
    done ;;
  all)
    install_cli
    for login in $(all_logins); do enrol "$login"; done ;;
  enrol)
    (( ${#LOGINS[@]} )) || { sed -n '2,12p' "$0" >&2; exit 2; }
    install_cli
    for login in "${LOGINS[@]}"; do enrol "$login"; done ;;
esac
