#!/usr/bin/env bash
# runtime/provisioning/secrets/store-enroll.sh — give an account its own
# key and its own encrypted store (agent-fabric ADR-038). Run by its
# PARENT, the fabric-coordinator login that provisioned it, from the
# parent's own checkout.
#
#   store-enroll.sh <login>... [--host <id>] [--dry-run]
#   store-enroll.sh --self                    the parent's own key and store,
#                                             recorded as the root of the chain
#
# For each login, idempotently:
#   1. the private repository <org>/secrets-<login> exists (the parent's gh;
#      AGENT_FABRIC_SECRETS_ORG, default the fabric's own org);
#   2. AS THE ACCOUNT, on the host it is placed on (runtime/hosts/registry.json,
#      reached through runtime/hostexec/hostexec — directly, or over ssh):
#      its key and store (`fabric-secrets store init --remote`), pushed;
#      its PUBLIC key exported to the parent;
#   3. the parent certifies that key with its own and writes
#      identities/keys/<login>.asc and lineage.json in this checkout;
#   4. the parent clones the child's store as its mirror
#      (~/.local/share/agent-fabric/children/<login>), to write into it.
# Then: commit identities/keys/, and the owner prints the account's sheet
# once, in a terminal of their own:
#   bin/fabric-host <host> run --as <login> --tty -- \
#     projects/agent-fabric/bin/fabric-secrets store paper
#
# No step needs the parent and the child on one host, and no value
# crosses between them: only a public key and ciphertext do.
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../.." && pwd)"
HOSTS="${AGENT_FABRIC_HOSTS_REGISTRY:-$ROOT/runtime/hosts/registry.json}"
HX="${AGENT_FABRIC_HOSTEXEC:-$ROOT/runtime/hostexec/hostexec}"
ORG="${AGENT_FABRIC_SECRETS_ORG:-gzapi-org}"
GH="${GH:-gh}"
STORE="$ROOT/tools/fabric/secret_store.py"
# The account's own fabric checkout, relative to ITS home (the worker
# starts there); the parent's checkout is not readable to it.
ACCOUNT_SECRETS="projects/agent-fabric/bin/fabric-secrets"

DRY=0; SELF=0; HOST_FLAG=""; LOGINS=()
while (( $# )); do
  a="$1"; shift
  case "$a" in
    --host) HOST_FLAG="$1"; shift ;;
    --host=*) HOST_FLAG="${a#--host=}" ;;
    --dry-run) DRY=1 ;;
    --self) SELF=1 ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "store-enroll: unknown flag $a" >&2; exit 2 ;;
    *) LOGINS+=("$a") ;;
  esac
done
say() { printf 'store-enroll: %s\n' "$*" >&2; }
die() { printf 'store-enroll: %s\n' "$*" >&2; exit 1; }
ME="$(id -un)"

# The base is the org on GitHub over SSH: the accounts' project
# checkouts are git@github.com (the fabric's own is https, being public),
# and no account has an HTTPS credential helper — an https remote to a
# private repository could not push. Read back on the coordinator's own
# enrolment: the push over SSH to its new private repository worked. AGENT_FABRIC_SECRETS_REMOTE_BASE replaces
# the base (the test's bare repositories).
repo_url() { echo "${AGENT_FABRIC_SECRETS_REMOTE_BASE:-git@github.com:$ORG}/secrets-$1.git"; }
ensure_repo() {  # the private repository, made by the parent when absent
  local name="$ORG/secrets-$1"
  "$GH" repo view "$name" >/dev/null 2>&1 && return 0
  (( DRY )) && { say "would: gh repo create $name --private"; return 0; }
  "$GH" repo create "$name" --private --description "agent-fabric: $1's encrypted secrets (ADR-038)" >/dev/null \
    || die "could not create $name (the parent's gh must be able to create a private repository in $ORG)"
}

if (( SELF )); then
  (( ${#LOGINS[@]} == 0 )) || die "--self takes no login"
  ensure_repo "$ME"
  (( DRY )) && { say "would: init my store, push it, certify --root"; exit 0; }
  python3 "$STORE" init --remote "$(repo_url "$ME")" >&2 || die "init failed"
  python3 "$STORE" push >&2 || die "push failed"
  python3 "$STORE" certify --root >&2 || die "certify --root failed"
  say "$ME: the root of the chain is recorded; commit identities/keys/, then print this account's sheet in a terminal of your own"
  exit 0
fi
(( ${#LOGINS[@]} )) || { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
python3 "$STORE" export-key >/dev/null 2>&1 || die "this login has no store yet: store-enroll.sh --self first (the parent certifies with its own key)"

host_of() {
  if [[ -n "$HOST_FLAG" ]]; then echo "$HOST_FLAG"; return; fi
  python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print((r.get("placement") or {}).get(sys.argv[2], ""))' "$HOSTS" "$1"
}
as_login() { local login="$1"; shift; "$HX" "$(host_of "$login")" --as "$login" -- "$@"; }

fail=0
for login in "${LOGINS[@]}"; do
  [[ "$login" == "$ME" ]] && { say "$login: that is this login; use --self"; fail=1; continue; }
  host="$(host_of "$login")"
  [[ -n "$host" ]] || { say "$login: not placed in runtime/hosts/registry.json (or name --host)"; fail=1; continue; }
  ensure_repo "$login"
  if (( DRY )); then say "would: on $host as $login: store init --remote $(repo_url "$login"), push, export-key; certify; mirror"; continue; fi
  as_login "$login" "$ACCOUNT_SECRETS" store init --remote "$(repo_url "$login")" >&2 \
    || { say "$login: init failed on $host"; fail=1; continue; }
  as_login "$login" "$ACCOUNT_SECRETS" store push >&2 || { say "$login: push failed"; fail=1; continue; }
  pub="$(mktemp)"
  if ! as_login "$login" "$ACCOUNT_SECRETS" store export-key > "$pub" || ! grep -q "BEGIN PGP PUBLIC KEY BLOCK" "$pub"; then
    rm -f "$pub"; say "$login: its public key did not come back"; fail=1; continue
  fi
  python3 "$STORE" certify "$login" "$pub" >&2 || { rm -f "$pub"; say "$login: certification failed"; fail=1; continue; }
  rm -f "$pub"
  mirror="$HOME/.local/share/agent-fabric/children/$login"
  if [[ -d "$mirror/.git" ]]; then
    if ! git -C "$mirror" pull -q --ff-only origin main >&2; then say "$login: its mirror could not be brought up to date"; fail=1; continue; fi
  else
    mkdir -p "$(dirname "$mirror")"
    if ! git clone -q "$(repo_url "$login")" "$mirror" >&2; then say "$login: mirror clone failed"; fail=1; continue; fi
  fi
  say "$login: key certified, store at $(repo_url "$login"), mirrored; the owner prints its sheet: bin/fabric-host $host run --as $login --tty -- $ACCOUNT_SECRETS store paper"
done
(( DRY )) || say "commit identities/keys/ (the certified keys and lineage.json)"
exit "$fail"
