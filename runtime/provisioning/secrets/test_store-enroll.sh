#!/usr/bin/env bash
# runtime/provisioning/secrets/test_store-enroll.sh — the parent gives an
# account its key and store (ADR-038) through the host executor, as it
# would on another host: the account is a separate scratch home and
# keyring reached only through a fake hostexec, the repositories are bare
# ones standing in for GitHub, and the fabric checkout is a scratch copy.
# Each keyring is OUTSIDE its home: a GNUPGHOME equal to $HOME/.gnupg is
# the account's default and shares the real gpg-agent.
set -uo pipefail
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"
PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; [[ -n "${2:-}" ]] && echo "$2" | sed 's/^/      /'; }
T="$(mktemp -d)"
REAL_KEYS=~/.gnupg/private-keys-v1.d; before="$(ls "$REAL_KEYS" 2>/dev/null | sort)"
cleanup() { for g in "$T/parent-gnupg" "$T/kid-gnupg"; do gpgconf --homedir "$g" --kill all 2>/dev/null; done; rm -rf "$T"; }
trap cleanup EXIT
FAB="$T/fabric"; mkdir -p "$FAB/identities/keys" "$T/remotes" "$T/bin"
for r in parent kid; do mkdir -p "$T/$r/projects" "$T/$r-gnupg"; chmod 700 "$T/$r-gnupg"; done
ln -s "$ROOT" "$T/kid/projects/agent-fabric"          # the account's own checkout, from its home
cat > "$T/hosts.json" <<J
{"version": 1, "hosts": {"far-host": {"ssh": "op@far", "operator": "op", "fabric": "$FAB"}}, "placement": {"kid": "far-host"}}
J
# The host executor: runs the command as "kid", in kid's home, with kid's keyring.
cat > "$T/bin/hostexec" <<S
#!/usr/bin/env bash
echo "hostexec \$*" >> "$T/calls"
[[ "\$1" == far-host && "\$2" == --as && "\$3" == kid && "\$4" == -- ]] || { echo "unexpected: \$*" >&2; exit 9; }
shift 4
[[ -e "$T/fail-push" && "\$*" == *"store push"* ]] && { echo "push rejected" >&2; exit 1; }
cd "$T/kid" && env -u CLAUDECODE HOME="$T/kid" GNUPGHOME="$T/kid-gnupg" AGENT_FABRIC_ROOT="$FAB" GIT_CONFIG_GLOBAL="$T/kid/.gc" "\$@"
S
# gh: "repo view" fails until "repo create" makes the bare repository.
cat > "$T/bin/gh" <<S
#!/usr/bin/env bash
echo "gh \$*" >> "$T/calls"
name="\${3##*/}"
case "\$1 \$2" in
  "repo view") [[ -d "$T/remotes/\$name.git" ]] ;;
  "repo create") git init -q --bare -b main "$T/remotes/\$name.git" ;;
  "repo edit") [[ ! -e "$T/fail-edit" ]] ;;
  *) exit 9 ;;
esac
S
chmod +x "$T/bin/"*
P() { env -u CLAUDECODE HOME="$T/parent" GNUPGHOME="$T/parent-gnupg" AGENT_FABRIC_ROOT="$FAB" GIT_CONFIG_GLOBAL="$T/parent/.gc" \
      AGENT_FABRIC_HOSTS_REGISTRY="$T/hosts.json" AGENT_FABRIC_HOSTEXEC="$T/bin/hostexec" GH="$T/bin/gh" \
      AGENT_FABRIC_SECRETS_REMOTE_BASE="$T/remotes" "$@"; }
E="$ROOT/runtime/provisioning/secrets/store-enroll.sh"

echo "store-enroll: the parent first"
out="$(P "$E" kid 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && grep -q "no store yet" <<<"$out" && ok "a parent without its own store is refused" || bad "no parent store (rc=$rc)" "$out"
out="$(P "$E" --self 2>&1)"; rc=$?
# An id's time is its birth; here, the home's creation time to the millisecond.
born_ms() { date -d "$(stat -c %w "$1")" +%s%3N; }
id_ms() { printf '%d' "0x$(tr -d - <<<"$1" | cut -c1-12)"; }
lid() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(a for a, r in d.items() if r["login"] == sys.argv[2]))' "$FAB/identities/keys/lineage.json" "$1"; }
PID="$(lid "$(id -un)" 2>/dev/null)"
[[ $rc -eq 0 && -n "$PID" && -d "$T/remotes/agent-fabric-secrets-$PID.git" ]] && python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert list(d.values())[0]["parent"] is None' "$FAB/identities/keys/lineage.json" \
  && ok "--self: the parent's repository, named by its agent id, its store and root key" || bad "--self (rc=$rc)" "$out"
[[ "$(id_ms "$PID")" == "$(born_ms "$T/parent")" ]] && ok "…its id's time is its home's creation time" || bad "parent birth" "$PID vs $(stat -c %w "$T/parent")"

echo "store-enroll: an account on another host"
# Review of #64, P2: a first run that stops after init (its push rejected)
# leaves the id in the account's store; the re-run takes it, never a new one.
touch "$T/fail-push"
out="$(P "$E" kid 2>&1)"; rc=$?
rm -f "$T/fail-push"
first_id="$(cat "$T/kid/.local/share/agent-fabric/secrets/.agent-id" 2>/dev/null)"
[[ $rc -eq 1 && -n "$first_id" ]] && grep -q "kid: push failed" <<<"$out" && ok "a first run whose push fails stops after init, the id in the account's store" || bad "failed push (rc=$rc)" "$out"
out="$(P "$E" kid 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -qE "kid: agent [0-9a-f-]{36}, key certified" <<<"$out" && ok "the child gets its key and store, and is certified" || bad "enrol (rc=$rc)" "$out"
grep -q "hostexec far-host --as kid" "$T/calls" && ok "…every account step went through the host executor to its placed host" || bad "no hostexec" "$(cat "$T/calls")"
KID="$(lid kid 2>/dev/null)"
[[ -n "$KID" && "$KID" == "$first_id" ]] && ok "…the re-run enrols it under the id its store already held" || bad "re-run id" "$KID vs $first_id"
grep -qF -- "--description agent-fabric secrets. Linux login: kid. Agent id: $KID." "$T/calls" && ok "…its repository's description gives the Linux login and the agent id" || bad "description" "$(grep 'repo create' "$T/calls")"
[[ -n "$KID" && -d "$T/remotes/agent-fabric-secrets-$KID.git" ]] && ok "…its repository is named by its agent id" || bad "child repo" "$(ls "$T/remotes")"
[[ -n "$KID" && "$(id_ms "$KID")" == "$(born_ms "$T/kid")" ]] && ok "…its id's time is ITS home's creation time, read on its host" || bad "child birth" "$KID"
[[ -d "$T/parent/.local/share/agent-fabric/children/$KID/.git" ]] && ok "…and the parent holds a mirror of the child's store" || bad "no mirror"
AGENT_FABRIC_ROOT="$FAB" python3 "$ROOT/tools/fabric/secret_store.py" verify >/dev/null 2>&1 && ok "…and lineage verifies" || bad "verify" "$(AGENT_FABRIC_ROOT="$FAB" python3 "$ROOT/tools/fabric/secret_store.py" verify 2>&1)"
out="$(P "$E" kid 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && [[ "$(gpg --homedir "$T/kid-gnupg" --list-secret-keys --with-colons 2>/dev/null | grep -c '^sec')" == 1 ]] && [[ "$(lid kid)" == "$KID" ]] \
  && ok "a second run keeps the child's one key and its id" || bad "re-run (rc=$rc)" "$out"
echo "top secret" | P python3 "$ROOT/tools/fabric/secret_store.py" put kid GH_TOKEN >/dev/null 2>&1 && ok "the parent can now write into the child's store" || bad "put after enrol"
out="$(P "$E" nobody 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && grep -q "nobody: not placed" <<<"$out" && ok "an unplaced login is refused by name" || bad "unplaced (rc=$rc)" "$out"

# A retried assign pushes the parent's own record that an earlier failed
# push left behind (the parent's remote rejects one push).
PR="$T/remotes/agent-fabric-secrets-$PID.git"
echo "sk-ant-oat01-tttttttttttttttttttt" | P python3 "$ROOT/tools/fabric/secret_store.py" template-set work >/dev/null 2>&1
printf '#!/bin/sh\nexit 1\n' > "$PR/hooks/pre-receive"; chmod +x "$PR/hooks/pre-receive"
out="$(P python3 "$ROOT/tools/fabric/secret_store.py" assign work kid 2>&1)"; rc=$?
rm -f "$PR/hooks/pre-receive"
out2="$(P python3 "$ROOT/tools/fabric/secret_store.py" assign work kid 2>&1)"; rc2=$?
git --git-dir "$PR" ls-tree -r --name-only main 2>/dev/null | grep -q "env/CLAUDE_ASSIGNED_KID.gpg" && [[ $rc -eq 1 && $rc2 -eq 0 ]] \
  && ok "a retried assign pushes the record a failed push left behind" || bad "assign catch-up (rc=$rc/$rc2)" "$out
$out2"

# The default remote is SSH: accounts reach GitHub with their own key, and
# none has an HTTPS credential helper for a private repository.
out="$(env -u AGENT_FABRIC_SECRETS_REMOTE_BASE HOME="$T/parent" GNUPGHOME="$T/parent-gnupg" AGENT_FABRIC_ROOT="$FAB" \
      AGENT_FABRIC_HOSTS_REGISTRY="$T/hosts.json" AGENT_FABRIC_HOSTEXEC="$T/bin/hostexec" GH="$T/bin/gh" "$E" kid --dry-run 2>&1)"
grep -q "store init --agent-id $KID --remote git@github.com:gzapi-org/agent-fabric-secrets-$KID.git" <<<"$out" && ok "the default remote is SSH, the scheme every account can push with" || bad "default remote" "$out"

# A rename: the login, in lineage and in the description; nothing stored moves.
out="$(P "$E" --rename kid kiddo 2>&1)"; rc=$?
[[ $rc -eq 0 && "$(lid kiddo 2>/dev/null)" == "$KID" && -z "$(lid kid 2>/dev/null)" && -d "$T/remotes/agent-fabric-secrets-$KID.git" \
   && -f "$FAB/identities/keys/$KID.asc" && -d "$T/parent/.local/share/agent-fabric/children/$KID/.git" ]] \
  && grep -qF -- "repo edit gzapi-org/agent-fabric-secrets-$KID --description agent-fabric secrets. Linux login: kiddo. Agent id: $KID." "$T/calls" \
  && ok "--rename changes the login and the description; the id, key, repository and mirror stay" || bad "rename (rc=$rc)" "$out"
echo "x" | P python3 "$ROOT/tools/fabric/secret_store.py" put kiddo AFTER_RENAME >/dev/null 2>&1 && AGENT_FABRIC_ROOT="$FAB" python3 "$ROOT/tools/fabric/secret_store.py" verify >/dev/null 2>&1 \
  && ok "…the renamed agent is written to by its new login, and verifies" || bad "after rename"
touch "$T/fail-edit"
out="$(P "$E" --rename kiddo kid3 2>&1)"; rc=$?
rm -f "$T/fail-edit"
[[ $rc -eq 1 ]] && grep -q "description still names kiddo" <<<"$out" && ok "…a rename whose description edit fails exits 1 and says what is left" || bad "rename edit failure (rc=$rc)" "$out"

after="$(ls "$REAL_KEYS" 2>/dev/null | sort)"
[[ "$before" == "$after" ]] && ok "the account's own keyring is left as it was found" || bad "real keyring changed"
if (( FAIL )); then echo "test_store-enroll: $FAIL FAILED"; exit 1; fi
echo "test_store-enroll: OK — $PASS assertion(s) passed."
