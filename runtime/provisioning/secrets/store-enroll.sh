#!/usr/bin/env bash
# runtime/provisioning/secrets/store-enroll.sh — give an account its own
# key and its own encrypted store (agent-fabric ADR-038). Run by its
# PARENT, the fabric-coordinator login that provisioned it, from the
# parent's own checkout.
#
#   store-enroll.sh <login>... [--host <id>] [--born-now] [--dry-run]
#   store-enroll.sh --self                    the parent's own key and store,
#                                             recorded as the root of the chain
#   store-enroll.sh --rename <old> <new>      a login renamed: its lineage entry's
#                                             login and its repository's description
#
# Commands take logins; each resolves the login to the agent's id first,
# and what is stored (repository, files, folders) is named by that id
# (ADR-039). The repository's description carries both.
#
# For each login, idempotently:
#   0. its agent id (ADR-039): the one lineage.json already records for
#      the login, else the one its own store already holds (a run that
#      stopped before certification), else minted here — a UUIDv7 whose time is the account's
#      birth: its home directory's creation time, or with --born-now (a
#      new account, new-agent.sh) this moment;
#   1. the private repository <org>/agent-fabric-secrets-<id> exists (the
#      parent's gh; AGENT_FABRIC_SECRETS_ORG, default the fabric's own org);
#   2. AS THE ACCOUNT, on the host it is placed on (runtime/hosts/registry.json,
#      reached through runtime/hostexec/hostexec — directly, or over ssh):
#      its key and store (`fabric-secrets store init --agent-id --remote`),
#      pushed; its PUBLIC key exported to the parent;
#   3. the parent certifies that key with its own and writes
#      identities/keys/<id>.asc and lineage.json in this checkout;
#   4. the parent clones the child's store as its mirror
#      (~/.local/share/agent-fabric/children/<id>), to write into it.
# Then: commit identities/keys/, and write the account's recovery copy,
# encrypted to the owner's recovery key (identities/recovery.asc):
#   bin/fabric-host <host> run --as <login> -- \
#     projects/agent-fabric/bin/fabric-secrets store recovery-copy
# and the parent's `fabric-secrets store backup` carries it to Proton.
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

DRY=0; SELF=0; RENAME=0; BORN_NOW=0; HOST_FLAG=""; LOGINS=()
while (( $# )); do
  a="$1"; shift
  case "$a" in
    --host) HOST_FLAG="$1"; shift ;;
    --host=*) HOST_FLAG="${a#--host=}" ;;
    --dry-run) DRY=1 ;;
    --self) SELF=1 ;;
    --rename) RENAME=1 ;;
    --born-now) BORN_NOW=1 ;;
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
repo_url() { echo "${AGENT_FABRIC_SECRETS_REMOTE_BASE:-git@github.com:$ORG}/agent-fabric-secrets-$1.git"; }
ensure_repo() {  # the private repository, made by the parent when absent: <id> [<login>]
  local name="$ORG/agent-fabric-secrets-$1"
  "$GH" repo view "$name" >/dev/null 2>&1 && return 0
  (( DRY )) && { say "would: gh repo create $name --private"; return 0; }
  "$GH" repo create "$name" --private --description "$(describe "$2" "$1")" >/dev/null \
    || die "could not create $name (the parent's gh must be able to create a private repository in $ORG)"
}

# The id lineage.json records for a login, or nothing when it records no
# agent with that login (exit 3); read by the store tool, so from the same
# fabric checkout it certifies into. Any other failure — a lineage that
# cannot be read — fails the call: an empty answer would mint a second id.
# A caller in $( ) checks it: `aid="$(id_of X)" || exit 1`.
id_of() {
  local out rc; out="$(python3 "$STORE" id-of "$1" 2>&1)"; rc=$?
  (( rc == 0 )) && { printf '%s\n' "$out"; return 0; }
  (( rc == 3 )) && return 0
  say "$1: identities/keys/lineage.json could not be read (exit $rc): ${out##*$'\n'}; nothing made"; return 1
}
describe() { echo "agent-fabric secrets. Linux login: $1. Agent id: $2. (ADR-038, ADR-039)"; }
mint() { python3 "$STORE" mint-id "$1"; }

if (( RENAME )); then
  (( ${#LOGINS[@]} == 2 )) || die "--rename takes <old> <new>"
  old="${LOGINS[0]}"; new="${LOGINS[1]}"
  aid="$(id_of "$old")" || exit 1; [[ -n "$aid" ]] || die "$old: no agent with that login in identities/keys/lineage.json"
  (( DRY )) && { say "would: agent $aid: login $old -> $new in lineage.json and its repository's description"; exit 0; }
  python3 "$STORE" rename "$old" "$new" >&2 || die "rename failed"
  "$GH" repo edit "$ORG/agent-fabric-secrets-$aid" --description "$(describe "$new" "$aid")" >/dev/null \
    || die "agent $aid: the lineage says $new; its repository's description still names $old (re-run gh repo edit, nothing else)"
  say "agent $aid is now $new; nothing stored moves. Commit identities/keys/; the Linux account, its runtime state and its relay address are renamed on its host."
  exit 0
fi

if (( SELF )); then
  (( ${#LOGINS[@]} == 0 )) || die "--self takes no login"
  # As for a child: only "no id yet" (exit 3) may lead to minting.
  aid="$(python3 "$STORE" id 2>/dev/null)"; idrc=$?
  (( idrc == 0 || idrc == 3 )) || die "this store's agent id could not be read (exit $idrc); nothing made"
  [[ -n "$aid" ]] || { aid="$(id_of "$ME")" || exit 1; }
  if [[ -z "$aid" ]]; then
    if (( BORN_NOW )); then born=now; else born="$(stat -c %w "$HOME")"; fi
    aid="$(mint "$born")" || die "no birth for $ME: its home's creation time is unknown here ($born)"
  fi
  ensure_repo "$aid" "$ME"
  (( DRY )) && { say "would: init my store as agent $aid, push it, certify --root"; exit 0; }
  python3 "$STORE" init --agent-id "$aid" --remote "$(repo_url "$aid")" >&2 || die "init failed"
  python3 "$STORE" push >&2 || die "push failed"
  python3 "$STORE" certify --root >&2 || die "certify --root failed"
  say "$ME: agent $aid, the root of the chain, is recorded; commit identities/keys/, then fabric-secrets store recovery-copy and store backup"
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
  aid="$(id_of "$login")" || { fail=1; continue; }
  # A run that stopped after init and before certification left the id in
  # the account's store: minting again would be refused there forever.
  if [[ -z "$aid" ]]; then
    # Only "no id yet" (exit 3) lets the parent mint: any other failure to
    # read the account's store would mint an id its store then refuses,
    # after a repository had been made for it.
    aid="$(as_login "$login" "$ACCOUNT_SECRETS" store id 2>/dev/null)"; idrc=$?
    if (( idrc != 0 && idrc != 3 )); then say "$login: its store's agent id could not be read on $host (exit $idrc); nothing made"; fail=1; continue; fi
    (( idrc == 3 )) && aid=""
  fi
  # Read back from another host: only an id, or it names a repository.
  if [[ -n "$aid" && ! "$aid" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]]; then
    say "$login: its store answered an agent id that is not one: ${aid:0:60}"; fail=1; continue
  fi
  if [[ -z "$aid" ]]; then
    if (( BORN_NOW )); then born=now; else born="$(as_login "$login" sh -c 'stat -c %w "$HOME"')"; fi
    aid="$(mint "$born")" || { say "$login: no birth: its home's creation time is unknown on $host ($born)"; fail=1; continue; }
  fi
  ensure_repo "$aid" "$login"
  if (( DRY )); then say "would: on $host as $login: store init --agent-id $aid --remote $(repo_url "$aid"), push, export-key; certify; mirror"; continue; fi
  as_login "$login" "$ACCOUNT_SECRETS" store init --agent-id "$aid" --remote "$(repo_url "$aid")" >&2 \
    || { say "$login: init failed on $host"; fail=1; continue; }
  as_login "$login" "$ACCOUNT_SECRETS" store push >&2 || { say "$login: push failed"; fail=1; continue; }
  pub="$(mktemp)"
  if ! as_login "$login" "$ACCOUNT_SECRETS" store export-key > "$pub" || ! grep -q "BEGIN PGP PUBLIC KEY BLOCK" "$pub"; then
    rm -f "$pub"; say "$login: its public key did not come back"; fail=1; continue
  fi
  python3 "$STORE" certify "$login" "$pub" >&2 || { rm -f "$pub"; say "$login: certification failed"; fail=1; continue; }
  rm -f "$pub"
  mirror="$HOME/.local/share/agent-fabric/children/$aid"
  if [[ -d "$mirror/.git" ]]; then
    if ! git -C "$mirror" pull -q --ff-only origin main >&2; then say "$login: its mirror could not be brought up to date"; fail=1; continue; fi
  else
    mkdir -p "$(dirname "$mirror")"
    if ! git clone -q "$(repo_url "$aid")" "$mirror" >&2; then say "$login: mirror clone failed"; fail=1; continue; fi
  fi
  say "$login: agent $aid, key certified, store at $(repo_url "$aid"), mirrored; its recovery copy: bin/fabric-host $host run --as $login -- $ACCOUNT_SECRETS store recovery-copy"
done
(( DRY )) || say "commit identities/keys/ (the certified keys and lineage.json)"
exit "$fail"
