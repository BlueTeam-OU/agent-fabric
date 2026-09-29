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
[[ $rc -eq 0 && -d "$T/remotes/secrets-$(id -un).git" ]] && python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert list(d.values())[0]["parent"] is None' "$FAB/identities/keys/lineage.json" \
  && ok "--self: the parent's repository, store and root key" || bad "--self (rc=$rc)" "$out"

echo "store-enroll: an account on another host"
out="$(P "$E" kid 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && grep -q "kid: key certified" <<<"$out" && ok "the child gets its key and store, and is certified" || bad "enrol (rc=$rc)" "$out"
grep -q "hostexec far-host --as kid" "$T/calls" && ok "…every account step went through the host executor to its placed host" || bad "no hostexec" "$(cat "$T/calls")"
[[ -d "$T/parent/.local/share/agent-fabric/children/kid/.git" ]] && ok "…and the parent holds a mirror of the child's store" || bad "no mirror"
AGENT_FABRIC_ROOT="$FAB" python3 "$ROOT/tools/fabric/secret_store.py" verify >/dev/null 2>&1 && ok "…and lineage verifies" || bad "verify" "$(AGENT_FABRIC_ROOT="$FAB" python3 "$ROOT/tools/fabric/secret_store.py" verify 2>&1)"
out="$(P "$E" kid 2>&1)"; rc=$?
[[ $rc -eq 0 ]] && [[ "$(gpg --homedir "$T/kid-gnupg" --list-secret-keys --with-colons 2>/dev/null | grep -c '^sec')" == 1 ]] && ok "a second run keeps the child's one key" || bad "re-run (rc=$rc)" "$out"
echo "top secret" | P python3 "$ROOT/tools/fabric/secret_store.py" put kid GH_TOKEN >/dev/null 2>&1 && ok "the parent can now write into the child's store" || bad "put after enrol"
out="$(P "$E" nobody 2>&1)"; rc=$?
[[ $rc -eq 1 ]] && grep -q "nobody: not placed" <<<"$out" && ok "an unplaced login is refused by name" || bad "unplaced (rc=$rc)" "$out"

# The default remote is SSH: accounts reach GitHub with their own key, and
# none has an HTTPS credential helper for a private repository.
out="$(env -u AGENT_FABRIC_SECRETS_REMOTE_BASE HOME="$T/parent" GNUPGHOME="$T/parent-gnupg" AGENT_FABRIC_ROOT="$FAB" \
      AGENT_FABRIC_HOSTS_REGISTRY="$T/hosts.json" AGENT_FABRIC_HOSTEXEC="$T/bin/hostexec" GH="$T/bin/gh" "$E" kid --dry-run 2>&1)"
grep -q "store init --remote git@github.com:gzapi-org/secrets-kid.git" <<<"$out" && ok "the default remote is SSH, the scheme every account can push with" || bad "default remote" "$out"

after="$(ls "$REAL_KEYS" 2>/dev/null | sort)"
[[ "$before" == "$after" ]] && ok "the account's own keyring is left as it was found" || bad "real keyring changed"
if (( FAIL )); then echo "test_store-enroll: $FAIL FAILED"; exit 1; fi
echo "test_store-enroll: OK — $PASS assertion(s) passed."
