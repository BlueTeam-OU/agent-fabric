#!/usr/bin/env bash
# runtime/provisioning/new-agent.sh — give a role its own account on this
# host: everything the control plane can do without a person at a
# terminal, in order, idempotently, then the short list of what only a
# person can do. Run by a fabric-coordinator holder from its own login
# (the account steps go through sudo; the Doppler steps use the
# coordinator's own CLI token).
#
#   runtime/provisioning/new-agent.sh <login> <role> [--host <id>] [--project <id>]... [--claude VERSION|stable|latest] [--dry-run]
#
#   new-agent.sh <login> <role> --project <id> --project <id>
#   new-agent.sh <login> <role> --host <host-id> --project <id>      # on another host
#
# TWO HALVES (review, 2026-09-16). This script is the ORCHESTRATOR: it
# runs on the coordinator's host and keeps what only the coordinator
# holds — the registry, the Doppler administration, the API keys. The
# HOST half, runtime/provisioning/new-agent-worker.sh, runs on the host
# the account is placed on (runtime/hosts/registry.json; --host names a
# new placement) through runtime/hostexec/hostexec — directly on this
# host, over ssh to any other — in two phases around the Doppler steps:
# `prepare` (0-4) and `finish` (6-10). The host names itself (`hostname
# -s`, checked against the registry id) and the coordinator never stamps
# a host it is not on.
#
# WHY THIS EXISTS. The host runbook (the managed project's docs/host/
# PROVISIONING.md) is twelve sections a person walks by hand, and twice
# on 2026-09-15 an account was walked through it in a session and came
# out short: a claude binary never installed, a root-owned ~/.local/bin,
# the GitHub host key never trusted so every SSH step failed as a
# password prompt, pnpm and node_modules absent, and — the one that
# mattered — a fill-from that copied the coordinator's admin keys into
# the new account's config. Each of those is one line here, checked
# before it is done, so the second account costs what the first did.
#
# WHAT IT DOES, in order (each step is skipped when already true):
#   0. the host: what this AppVM must already have and what it can hold.
#      A Qubes AppVM keeps only /home and /usr/local across a reboot; a
#      package is the TemplateVM's (dnf there, not here). So: the rpm
#      tools the fabric and the projects use (git, gh, node, npm,
#      python3, jq, gpg) are audited and a missing one is named with its
#      package for the template; doppler goes to /usr/local/bin once
#      (persistent), the account's own tools go under its ~/.local. What
#      a PROJECT needs of the host beyond that is the project's own
#      integration/provisioning/host-check.sh, run in finish. [worker: prepare]
#   1. the Linux account (useradd), home 700, the shared-cache group, and the
#      account persisted across the host's reboot (linger; on Qubes the record
#      snapshot under /rw — persist-accounts.sh)
#   2. ~/.ssh ~/.claude ~/.config/gh ~/.local/{bin,share}, owned by the
#      account; claude and ori installed AS THE ACCOUNT the way their
#      vendors say — `curl -fsSL https://claude.ai/install.sh | bash -s --
#      <version>` — at the version the fleet pins in
#      runtime/claude-code/harness.json (what `fabric-ctl … upgrade
#      claude` brings every account to), the vendor's latest only when no
#      pin is readable; --claude overrides it with a version, stable or
#      latest — and `curl -fsSL
#      https://openrouter.ai/labs/ori/install.sh | bash` (stable channel;
#      it has no version pin) — both land in ~/.local/bin. An installer
#      that fails fails the script: nothing is copied from another
#      account in its place (owner, 2026-09-16).
#   3. github.com's published host keys (runtime/provisioning/github-host-keys)
#      in the account's known_hosts — never a keyscan
#   4. ~/projects/agent-fabric cloned over https (the fabric is public;
#      the account has no key yet) — enrolment reads the account's own
#      checkout for fabric-secrets                       [worker: prepare, 1-4]
#   5. Doppler enrolment: enroll.sh <login>, fill-from <coordinator>,
#      issue-openrouter-keys, issue-openai-keys, then sync — GH_TOKEN, the
#      relay token, the SSH key pair, the git identity strings, a key of
#      the account's own on each API                     [the coordinator]
#   6. every --project cloned AS THE ACCOUNT over SSH from the remote the
#      registry names (the key from step 5 is what makes this work)
#   7. bootstrap.sh as the account (workspace CLAUDE.md, hooks, agent
#      files, skills, core.hooksPath on every clone)
#   8. bin/fabric-role bind <role>, from the account's login shell
#   9. toolchain per project, from its lockfile: pnpm (installed under
#      ~/.local) and `pnpm install`, or `npm install`
#  10. verify: fabric-secrets status, gh, ssh to GitHub, git identity,
#      launch --print for both providers — and print what remains for a
#      person: the GPG secret key (a passphrase prompt; the runbook §4),
#      ~/.claude/.credentials.json for the plain-claude path (a
#      credential copy a classifier refuses an agent; §5), and the
#      workspace-trust dialog at the first interactive launch. [worker: finish, 6-10]
#
# NEVER: a secret value on the terminal (enroll.sh keeps them inside
# doppler calls); a copy of the coordinator's admin or provisioning keys
# (enroll.sh fill-from excludes them); a guess at a port offset (a row in
# the project's table is devex-tooling's to add, and the registry marks
# the name per login so fill-from never inherits one).
#
# FAILURE SEMANTICS (review, 2026-09-16 — before this, `run x; say done`
# announced success whatever x returned, and a failed useradd, clone,
# bootstrap or bind left a half-made account while later steps went on).
# Not `set -e`: half the lines here are questions. Every step names one
# of three:
#   must         the step is the account: a failure stops the script,
#                naming the step; nothing after it runs
#   probe        a question, never an error (is X present?)
#   best_effort  worth doing, not worth stopping for: a failure is one
#                warning line and the script goes on
# A pipeline that ends in sed/grep is judged by its FIRST command's
# status (${PIPESTATUS[0]}), never by the filter's.
# test_new-agent.sh runs the real sequence against fakes and injects a
# failure at each must.
set -uo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
REGISTRY="$ROOT/projects/registry.json"
ENROLL="$ROOT/runtime/provisioning/secrets/enroll.sh"
HOSTS="${AGENT_FABRIC_HOSTS_REGISTRY:-$ROOT/runtime/hosts/registry.json}"
HX="$ROOT/runtime/hostexec/hostexec"
DRY=0; LOGIN=""; ROLE=""; PROJECTS=(); CLAUDE_TARGET=""; HOST=""
while (( $# )); do
    case "$1" in
        --dry-run) DRY=1 ;;
        --host) HOST="$2"; shift ;;
        --host=*) HOST="${1#--host=}" ;;
        --claude) CLAUDE_TARGET="$2"; shift ;;
        --claude=*) CLAUDE_TARGET="${1#--claude=}" ;;
        --project) PROJECTS+=("$2"); shift ;;
        --project=*) PROJECTS+=("${1#--project=}") ;;
        -h|--help) sed -n '2,52p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) echo "new-agent: unknown flag $1" >&2; exit 2 ;;
        *) if [[ -z "$LOGIN" ]]; then LOGIN="$1"; elif [[ -z "$ROLE" ]]; then ROLE="$1"; else echo "new-agent: unexpected argument $1" >&2; exit 2; fi ;;
    esac
    shift
done
[[ -n "$LOGIN" && -n "$ROLE" ]] || { echo "usage: new-agent.sh <login> <role> [--host <id>] [--project <id>]... [--claude VERSION|stable|latest] [--dry-run]" >&2; exit 2; }
# The value reaches the worker's as_login eval inside single quotes, so a
# suffix may carry no quote, semicolon or other shell character — only
# what a real pre-release or build tag holds (review of #34).
[[ -z "$CLAUDE_TARGET" || "$CLAUDE_TARGET" =~ ^(stable|latest|[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?)$ ]] || { echo "new-agent: --claude takes stable, latest or a version" >&2; exit 2; }

say() { printf 'new-agent: %s\n' "$*" >&2; }
die() { printf 'new-agent: %s\n' "$*" >&2; exit 1; }
run() { if (( DRY )); then say "would: $*"; else "$@"; fi; }
must() { run "$@" || die "step failed: $* — nothing after it ran; fix the cause and re-run (every step is idempotent)"; }
probe() { "$@"; }
best_effort() { run "$@" || say "warning: $* failed; continuing"; }
COORD="$(id -un)"
[[ "$COORD" != root ]] || die "run this as the fabric-coordinator login, not root: the Doppler steps use your own CLI token."

# ---- what is asked for must exist in the fabric --------------------------
[[ -f "$ROOT/identities/roles/$ROLE/charter.md" ]] || die "no role '$ROLE' under identities/roles/ (bin/fabric-role list)."
declare -A REMOTE
for pid in "${PROJECTS[@]+"${PROJECTS[@]}"}"; do
    r="$(python3 -c '
import json, sys
d = json.load(open(sys.argv[1])); p = (d.get("projects") or {}).get(sys.argv[2])
if not p: sys.exit(1)
print(next((x for x in p["remotes"] if x.startswith("git@")), p["remotes"][0]))' "$REGISTRY" "$pid")" || die "project '$pid' is not in projects/registry.json — register it first."
    REMOTE["$pid"]="$r"
done

LOG="$(mktemp)"; trap 'rm -f "$LOG"' EXIT

# ---- the host the account lives on ------------------------------------------
# Placement is the registry's: an account already placed is provisioned
# there and nowhere else; a new account goes to --host, or to this host.
placed="$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print((r.get("placement") or {}).get(sys.argv[2], ""))' "$HOSTS" "$LOGIN")"
local_host="$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print(next((h for h,e in (r.get("hosts") or {}).items() if e.get("ssh") is None), ""))' "$HOSTS")"
if [[ -n "$placed" && -n "$HOST" && "$placed" != "$HOST" ]]; then die "$LOGIN is placed on $placed (runtime/hosts/registry.json); --host $HOST would make a second account of that name. Move the placement first, or drop --host."; fi
HOST="${HOST:-${placed:-$local_host}}"
[[ -n "$HOST" ]] || die "no host: name one with --host, or register this host (ssh null) in runtime/hosts/registry.json"
"$HX" --resolve "$HOST" >/dev/null || exit 1
# The host names itself; a name other than the id it was reached as is refused.
check="$("$HX" "$HOST" -- @fabric/runtime/provisioning/new-agent-worker.sh host-check "$LOGIN" 2>>"$LOG")" \
    || { tail -5 "$LOG" >&2; die "host $HOST: unreachable, or its worker did not run"; }
reported="${check%%$'\n'*}"
[[ "$reported" == "$HOST" ]] || die "host $HOST answers as '$reported'; the registry id is the host's short hostname (bin/fabric-host $HOST check)"
say "host $HOST$( [[ "$HOST" == "$local_host" ]] && echo " (this host)" || echo " (over ssh)" ); account $LOGIN, role $ROLE"
[[ -n "$placed" ]] || say "placement: add \"$LOGIN\": \"$HOST\" to runtime/hosts/registry.json placement (bin/fabric-status on the account reports drift until it is there)"
worker() {  # worker <phase> <args...>: the host half, on $HOST
    "$HX" "$HOST" -- @fabric/runtime/provisioning/new-agent-worker.sh "$@"
}
clone_args=(); for pid in "${PROJECTS[@]+"${PROJECTS[@]}"}"; do clone_args+=(--clone "$pid=${REMOTE[$pid]}"); done
dry_arg=(); (( DRY )) && dry_arg=(--dry-run)

# ---- 0-4 on the host ------------------------------------------------------------
worker prepare "$LOGIN" "$ROLE" ${CLAUDE_TARGET:+--claude "$CLAUDE_TARGET"} "${dry_arg[@]}" || die "the host half stopped (above); nothing after it ran"

# ---- 5. Doppler enrolment ---------------------------------------------------
# A key of the account's own is minted once: issue-* replaces whatever the
# name holds, so a re-run must not mint again. The name's presence in the
# account's config is the check (names only; no value is read).
config_has() {  # config_has <name> — true when the account's config carries it
    # Asked THROUGH the account on its host: the recorded config name is
    # in its ~/.doppler; only the names are read, never a value.
    local cfg; cfg="$("$HX" "$HOST" --as "$LOGIN" -- doppler configure get enclave.config --plain --scope / 2>/dev/null || true)"
    [[ -n "$cfg" ]] || return 1
    doppler secrets --only-names --json --project agent-fabric --config "$cfg" 2>/dev/null | python3 -c 'import json,sys; sys.exit(0 if sys.argv[1] in json.load(sys.stdin) else 1)' "$1"
}
if (( DRY )); then say "would: enroll.sh $LOGIN; fill-from $COORD $LOGIN; issue-openrouter-keys and issue-openai-keys $LOGIN (each once)"
else
    # First pass: config + token + the strings. Its verification is
    # EXPECTED to report the keys missing (they are issued below), so its
    # exit status is not the fact here — what is, is that a config exists
    # for the account afterwards, which config_has proves through it.
    "$ENROLL" "$LOGIN" >"$LOG" 2>&1
    probe config_has AGENT_LOGIN || { tail -5 "$LOG" >&2; die "step failed: enroll.sh $LOGIN — no Doppler config holds the account (see above); nothing after it ran"; }
    "$ENROLL" fill-from "$COORD" "$LOGIN" 2>&1 | grep -v "^gathered\|^upload" | sed 's/^/   /' >&2
    (( PIPESTATUS[0] == 0 )) || die "step failed: enroll.sh fill-from $COORD $LOGIN; nothing after it ran"
    # Both API keys are per login (projects/registry.json agent_env), so
    # fill-from never copies them and presence means "issued".
    if probe config_has OPENROUTER_API_KEY; then say "   OpenRouter key: present (issued once; not minted again)"
    else "$ENROLL" issue-openrouter-keys "$LOGIN" 2>&1 | tail -1 | sed 's/^/   /' >&2; (( PIPESTATUS[0] == 0 )) || die "step failed: enroll.sh issue-openrouter-keys $LOGIN; nothing after it ran"; fi
    if probe config_has OPENAI_API_KEY; then say "   OpenAI key: present (issued once; not minted again)"
    else "$ENROLL" issue-openai-keys "$LOGIN" 2>&1 | tail -1 | sed 's/^/   /' >&2; (( PIPESTATUS[0] == 0 )) || die "step failed: enroll.sh issue-openai-keys $LOGIN; nothing after it ran"; fi
    "$ENROLL" "$LOGIN" 2>&1 | grep -E "authenticated|signing key|verification|OK$|NOT OK" | sed 's/^/   /' >&2
    (( PIPESTATUS[0] == 0 )) || die "step failed: enroll.sh $LOGIN (sync and verify); nothing after it ran"
    say "5. enrolled; secrets synced"
fi


# ---- 6-10 on the host -----------------------------------------------------------
worker finish "$LOGIN" "$ROLE" "${clone_args[@]}" "${dry_arg[@]}" || die "the host half stopped (above); nothing after it ran"
