#!/usr/bin/env bash
# runtime/provisioning/test_new-agent.sh — new-agent.sh refuses what the
# fabric does not know, its dry run names every step without touching the
# host, and the REAL sequence — against fakes for sudo, useradd, getent,
# id, curl (the vendor installers), ssh-keyscan, git clone, doppler and
# enroll.sh, in a sandbox — stops where a step fails, names it, runs
# nothing after it, and converges on the re-run (review, 2026-09-16).
# Root, Doppler and the network are what the fakes stand in for.
set -uo pipefail
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
UNDER_TEST="$HERE/new-agent.sh"
PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; [[ -n "${2:-}" ]] && echo "$2" | sed 's/^/      /'; }
SANDBOX="$(mktemp -d)"; trap '[[ -n "${KEEP_SANDBOX:-}" ]] || rm -rf "$SANDBOX"' EXIT
# A fixture fabric: the real roles and registry, a fake claude to copy from.
FAB="$SANDBOX/fabric"; mkdir -p "$FAB/runtime/provisioning/secrets" "$FAB/identities" "$FAB/projects" "$SANDBOX/home/.local/bin"
cp -r "$ROOT/identities/roles" "$FAB/identities/"; cp "$ROOT/projects/registry.json" "$FAB/projects/"
cp "$UNDER_TEST" "$HERE/new-agent-worker.sh" "$HERE/persist-accounts.sh" "$ROOT/runtime/provisioning/github-host-keys" "$FAB/runtime/provisioning/"
cp -r "$ROOT/runtime/hostexec" "$FAB/runtime/"; cp -r "$ROOT/runtime/provisioning/platform" "$FAB/runtime/provisioning/"; mkdir -p "$FAB/runtime/claude-code"; cp "$ROOT/runtime/claude-code/harness.json" "$FAB/runtime/claude-code/"
printf '#!/bin/sh\necho fake\n' > "$SANDBOX/home/.local/bin/claude"; chmod +x "$SANDBOX/home/.local/bin/claude"
# The host registry the orchestrator reads: this host (direct) and a far
# one reached over a fake ssh that runs the same worker here.
LOCAL="$(hostname -s)"; HOSTS="$SANDBOX/hosts.json"
cat > "$HOSTS" <<EOF
{"version": 1,
 "hosts": {"$LOCAL": {"platform": "fedora-qubes", "ssh": null, "operator": "$(id -un)", "fabric": "$FAB"},
           "far-host": {"platform": "debian", "ssh": "op@far.example", "operator": "op", "fabric": "$FAB"}},
 "placement": {"placed-elsewhere": "far-host"}}
EOF
export AGENT_FABRIC_HOSTS_REGISTRY="$HOSTS"
run() { HOME="$SANDBOX/home" bash "$FAB/runtime/provisioning/new-agent.sh" "$@" 2>&1; }

echo "new-agent: refusals"
out="$(run 2>&1)"; [[ $? -eq 2 ]] && grep -q "^usage:" <<<"$out" && ok "no arguments: usage, exit 2" || bad "usage" "$out"
out="$(run some-login no-such-role --dry-run)"; [[ $? -eq 1 ]] && grep -q "no role 'no-such-role'" <<<"$out" && ok "an unknown role is refused before anything runs" || bad "unknown role" "$out"
out="$(run some-login backend-dev --project not-registered --dry-run)"; [[ $? -eq 1 ]] && grep -q "not in projects/registry.json" <<<"$out" && ok "an unregistered project is refused" || bad "unregistered project" "$out"
out="$(run some-login backend-dev --bogus --dry-run)"; [[ $? -eq 2 ]] && ok "an unknown flag is a usage error" || bad "unknown flag" "$out"
out="$(run placed-elsewhere backend-dev --host "$LOCAL" --dry-run)"; [[ $? -eq 1 ]] && grep -q "is placed on far-host" <<<"$out" && ok "an account placed on another host is not made again here" || bad "placement not enforced" "$out"
out="$(run some-login backend-dev --host nowhere --dry-run)"; [[ $? -eq 1 ]] && grep -q "unknown host 'nowhere'" <<<"$out" && ok "an unregistered host is refused" || bad "unknown host" "$out"

echo "new-agent: the dry run names every step and touches nothing"
out="$(run zz-fixture-login backend-dev --project gzapp --project agent-fabric --dry-run)"; rc=$?
[[ $rc -eq 0 ]] && ok "exits 0" || bad "rc=$rc" "$out"
for step in "useradd" "chmod 700" "mkdir -p" "curl -fsSL https://claude.ai/install.sh | bash -s -- " "curl -fsSL https://openrouter.ai/labs/ori/install.sh | bash" "append GitHub's published host keys" "git clone -q 'https://github.com/gzapi-org/agent-fabric.git'" "enroll.sh zz-fixture-login; fill-from" "issue-openrouter-keys and issue-openai-keys" "git clone -q 'git@github.com:gzapi-org/gzapp.git'" "bootstrap.sh" "fabric-role bind 'backend-dev'"; do
    grep -qF "$step" <<<"$out" && ok "plans: $step" || bad "missing step: $step" "$out"
done
grep -q "dry run: nothing verified" <<<"$out" && ok "…and verifies nothing" || bad "verified in dry run" "$out"
grep -q "would: store-enroll.sh zz-fixture-login --host" <<<"$out" && ok "…and names step 5b, the account's key and store (ADR-038)" || bad "5b not in the dry run" "$out"
! getent passwd zz-fixture-login >/dev/null && ok "no account was created" || bad "an account was created by a dry run"
grep -q "git@github.com" <<<"$out" && ok "a project clone uses the registry's SSH remote" || bad "remote" "$out"
! grep -qi "copied\|copy from" <<<"$out" && ok "no binary is ever copied from another account" || bad "a copy fallback is planned" "$out"
grep -q "^new-agent: 0\. [a-z-]*: host tools present\|^new-agent: 0\. [a-z-]*: this" <<<"$out" && ok "the host audit runs first, naming the platform" || bad "no host audit" "$out"
# A PATH with everything the dry run needs except gh: the audit must name gh's Debian package and apt-get.
mkdir -p "$SANDBOX/nogh"; for t in bash python3 getent id sudo hostname readlink dirname basename cut grep sed head tail tr sort uniq mktemp cat env cp mkdir rm ls ln chmod tee wc awk xargs curl ssh git jq gpg node npm sha256sum stat pgrep timeout flock useradd usermod shred install; do
    src="$(command -v "$t" 2>/dev/null)"; [[ -n "$src" ]] && ln -sf "$src" "$SANDBOX/nogh/$t"; done
out_deb="$(AGENT_FABRIC_PLATFORM=debian PATH="$SANDBOX/nogh" run zz-fixture-login backend-dev --dry-run 2>&1)"
grep -q "^new-agent: 0\. debian: this host lacks .*gh.*: sudo apt-get install" <<<"$out_deb" && ok "the Debian profile names the missing tool's package and apt-get" || bad "debian profile" "$out_deb"
grep -q "^new-agent: host $LOCAL (this host)" <<<"$out" && grep -q "placement: add \"zz-fixture-login\"" <<<"$out" && ok "the host is named, and a missing placement is asked for" || bad "host line" "$out"
out="$(run some-login backend-dev --claude 9.9 --dry-run)"; [[ $? -eq 2 ]] && ok "--claude takes stable, latest or a full version" || bad "bad --claude accepted" "$out"
out="$(run some-login backend-dev --claude "1.2.3-x';id;'" --dry-run)"; [[ $? -eq 2 ]] && ok "--claude with shell characters in its suffix is refused" || bad "--claude injection accepted" "$out"
out="$(run zz-fixture-login backend-dev --claude 2.1.282-beta.1 --dry-run)"; grep -q "install.sh | bash -s -- 2.1.282-beta.1" <<<"$out" && ok "…while a real pre-release suffix still passes" || bad "pre-release refused" "$out"
out="$(run zz-fixture-login backend-dev --claude latest --dry-run)"; grep -q "install.sh | bash -s -- latest" <<<"$out" && ok "--claude latest reaches the installer" || bad "--claude ignored" "$out"
PIN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["claude"])' "$ROOT/runtime/claude-code/harness.json")"
out="$(run zz-fixture-login backend-dev --dry-run)"; grep -q "install.sh | bash -s -- $PIN\$" <<<"$out" && ok "no --claude: the fleet's pinned version ($PIN) reaches the installer" || bad "default is not the pin" "$(grep install.sh <<<"$out")"
printf '{"claude": "2.1.282'"'"'; touch /tmp/pwned; '"'"'"}' > "$FAB/runtime/claude-code/harness.json"
out="$(run zz-fixture-login backend-dev --dry-run)"; rc=$?
[[ $rc -ne 0 ]] && grep -q "is not a version; nothing installed" <<<"$out" && ! grep -q "install.sh | bash" <<<"$out" && ok "a pin that is not a version is refused before it reaches the installer's command line" || bad "bad pin accepted (rc=$rc)" "$(grep -iE "pin|install" <<<"$out")"
rm -f "$FAB/runtime/claude-code/harness.json"
out="$(run zz-fixture-login backend-dev --dry-run)"
grep -q "no readable pin .* the vendor's latest instead" <<<"$out" && grep -q "install.sh | bash -s -- latest" <<<"$out" && ok "no pin: latest, and that is said" || bad "silent fallback" "$(grep -iE "pin|install" <<<"$out")"
cp "$ROOT/runtime/claude-code/harness.json" "$FAB/runtime/claude-code/"

# ---- the real sequence, against fakes, with a failure injected at each must ----
# sudo drops `-n -u X -H` and runs the rest as this user; useradd makes a
# sandbox home; getent answers for it; curl "installs" claude/ori from a
# fixture; ssh-keyscan answers a fixture key; git clones from a local bare
# repo (AGENT_FABRIC_CLONE_URL and a registry pointing at it); a fake
# enroll.sh records its calls and a fake doppler answers config_has. A
# fault file names one command the fakes must fail.
echo "new-agent: the real sequence, then a failure at each step"
SEQ="$SANDBOX/seq"; BIN="$SEQ/bin"; HOMES="$SEQ/home"; FAULT="$SEQ/fault"; CALLS="$SEQ/calls"; mkdir -p "$BIN" "$HOMES"
export PATH="$BIN:/usr/bin:/bin"
BARE="$SEQ/fabric.git"; git init -q --bare -b main "$BARE"
SRC="$SEQ/fabric-src"; mkdir -p "$SRC/runtime/claude-code" "$SRC/bin"
printf '#!/usr/bin/env bash\necho "bootstrap: ok"\n' > "$SRC/runtime/claude-code/bootstrap.sh"
printf '#!/usr/bin/env bash\ncase "$1" in status) echo "role      (none active)";; bind) echo "bound. role $2";; esac\n' > "$SRC/bin/fabric-role"
printf '#!/usr/bin/env bash\necho "fabric-secrets: OK"\n' > "$SRC/bin/fabric-secrets"
mkdir -p "$SRC/runtime/openrouter"; printf '#!/usr/bin/env bash\necho "launch: resolved profile x"\n' > "$SRC/runtime/openrouter/launch"
chmod +x "$SRC/runtime/claude-code/bootstrap.sh" "$SRC/bin/"* "$SRC/runtime/openrouter/launch"
git -C "$SRC" init -q -b main && git -C "$SRC" add -A && git -C "$SRC" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q -m init && git -C "$SRC" push -q "$BARE" HEAD:main
DEMO="$SEQ/demo.git"; git init -q --bare -b main "$DEMO"; d="$SEQ/demo-src"; mkdir -p "$d"; printf '{}' > "$d/package-lock.json"; git -C "$d" init -q -b main; git -C "$d" add -A; git -C "$d" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q -m init; git -C "$d" push -q "$DEMO" HEAD:main
python3 - "$FAB/projects/registry.json" "$DEMO" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["projects"]["demo"] = {"remotes": [sys.argv[2]], "license": "Apache-2.0"}; json.dump(d, open(sys.argv[1], "w"))
PY
fault_hit() { [[ -f "$FAULT" ]] && grep -qxF "$1" "$FAULT"; }
cat > "$BIN/sudo" <<STUB
#!/usr/bin/env bash
[[ "\$1" == -n ]] && shift; [[ "\$1" == true ]] && exit 0
[[ "\$1" == -u ]] && shift 2; [[ "\$1" == -H ]] && shift
# The fakes first, and never /usr/local/bin: a real claude or doppler there must not be what the fixture account runs.
args=(); for a in "\$@"; do
  [[ "\$a" == PATH=* ]] && a="PATH=$BIN:\${a#PATH=}" && a="\${a//\/usr\/local\/bin:/}"
  [[ "\$a" == AGENT_FABRIC_PATH=* ]] && a="AGENT_FABRIC_PATH=$BIN:\${a#AGENT_FABRIC_PATH=}" && a="\${a//\/usr\/local\/bin:/}"
  args+=("\$a"); done
echo "sudo \${args[*]}" >> "$CALLS"   # whole lines: a cap only moves where a long TMPDIR truncates an assertion away
grep -qsxF "\${args[0]}" "$FAULT" && { echo "fake: \${args[0]} failed (injected)" >&2; exit 1; }
[[ "\${args[0]}" == chown ]] && exit 0
exec "\${args[@]}"
STUB
cat > "$BIN/useradd" <<STUB
#!/usr/bin/env bash
login="\${@: -1}"; mkdir -p "$HOMES/\$login"; echo "\$login" >> "$SEQ/passwd"; echo "useradd \$login" >> "$CALLS"
STUB
# usermod: the subordinate-range allocation records itself and writes the
# range where the worker reads it back (AGENT_FABRIC_ETC), so the second
# run finds it and allocates nothing.
cat > "$BIN/usermod" <<STUB
#!/usr/bin/env bash
echo "usermod \$*" >> "$CALLS"
login="\${@: -1}"; r=""; while [[ \$# -gt 0 ]]; do [[ "\$1" == --add-subuids ]] && r="\$2"; shift; done
[[ -n "\$r" ]] && mkdir -p "$SANDBOX/persist/etc" && printf '%s:%s:%s\n' "\$login" "\${r%-*}" "\$(( \${r#*-} - \${r%-*} + 1 ))" | tee -a "$SANDBOX/persist/etc/subuid" >> "$SANDBOX/persist/etc/subgid"
STUB
cat > "$BIN/loginctl" <<STUB
#!/usr/bin/env bash
echo "loginctl \$*" >> "$CALLS"
STUB
cat > "$BIN/getent" <<STUB
#!/usr/bin/env bash
case "\$1" in
  passwd) grep -qsxF "\$2" "$SEQ/passwd" && echo "\$2:x:1000:1000::$HOMES/\$2:/bin/bash" ;;
  group) exit 2 ;;
esac
STUB
cat > "$BIN/id" <<'STUB'
#!/usr/bin/env bash
[[ "$1" == -gn ]] && { echo staff; exit 0; }
[[ "$1" == -nG ]] && { echo ""; exit 0; }
exec /usr/bin/id "$@"
STUB
cat > "$BIN/curl" <<STUB
#!/usr/bin/env bash
echo "curl \$*" >> "$CALLS"
grep -qsxF curl "$FAULT" && exit 22
case "\$*" in
  *claude-code-releases/latest*) echo "9.9.9" ;;
  *claude.ai/install.sh*) printf 'v="\${1:-9.9.9}"; mkdir -p ~/.local/share/claude/versions ~/.local/bin; printf "#!/bin/sh\\\\necho %%s-fake\\\\n" "\$v" > ~/.local/share/claude/versions/\$v; chmod +x ~/.local/share/claude/versions/\$v; ln -sf ~/.local/share/claude/versions/\$v ~/.local/bin/claude\\n' ;;
  *ori/install.sh*) printf 'mkdir -p ~/.local/bin; printf "#!/bin/sh\\\\necho ori-0.1-fake\\\\n" > ~/.local/bin/ori; chmod +x ~/.local/bin/ori\\n' ;;
  *) exit 22 ;;
esac
STUB
cat > "$BIN/ssh-keyscan" <<STUB
#!/usr/bin/env bash
echo "ssh-keyscan \$*" >> "$CALLS"; echo "fake: ssh-keyscan must never be called (the host keys are committed)" >&2; exit 99
STUB
cat > "$BIN/doppler" <<STUB
#!/usr/bin/env bash
case "\$*" in
  "configure get enclave.config --plain --scope /") [[ -f "$SEQ/enrolled" ]] && printf 'agents_x' || exit 1 ;;
  "secrets --only-names --json "*) [[ -f "$SEQ/enrolled" ]] && cat "$SEQ/enrolled" || echo '{}' ;;
  *) exit 9 ;;
esac
STUB
cat > "$SEQ/enroll.sh" <<STUB
#!/usr/bin/env bash
echo "enroll \$*" >> "$CALLS"
grep -qsxF "enroll \$1" "$FAULT" && { echo "enroll: injected failure" >&2; exit 1; }
case "\$1" in
  fill-from) exit 0 ;;
  issue-openrouter-keys) python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["OPENROUTER_API_KEY"]={}; json.dump(d,open(sys.argv[1],"w"))' "$SEQ/enrolled" ;;
  issue-openai-keys) python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["OPENAI_API_KEY"]={}; json.dump(d,open(sys.argv[1],"w"))' "$SEQ/enrolled" ;;
  *) [[ -f "$SEQ/enrolled" ]] || echo '{"AGENT_LOGIN": {}}' > "$SEQ/enrolled"; echo "enroll: verification OK" ;;
esac
STUB
printf '#!/usr/bin/env bash\necho "gh auth: Logged in to github.com"\n' > "$BIN/gh"
cat > "$BIN/git" <<STUB
#!/usr/bin/env bash
[[ "\$1" == clone ]] && grep -qsxF git "$FAULT" && { echo "fake git: clone failed (injected)" >&2; exit 128; }
exec /usr/bin/git "\$@"
STUB
printf '#!/usr/bin/env bash\n[[ "$1" == ci ]] && mkdir -p node_modules; exit 0\n' > "$BIN/npm"
printf '#!/usr/bin/env bash\nexit 0\n' > "$BIN/gpg"
chmod +x "$BIN"/* "$SEQ/enroll.sh"
SSHLOG="$SEQ/ssh.log"
# The far host is this machine behind a fake ssh, so it must answer as
# itself: a fake hostname, first on the remote PATH, says far-host.
mkdir -p "$SEQ/farbin"; printf '#!/usr/bin/env bash\n[[ "$1" == -s ]] && { echo far-host; exit 0; }; exec /usr/bin/hostname "$@"\n' > "$SEQ/farbin/hostname"; chmod +x "$SEQ/farbin/hostname"
cat > "$BIN/ssh" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$SSHLOG"; args=("\$@"); PATH="$SEQ/farbin:\$PATH" exec bash -c "\${args[-1]}"
STUB
chmod +x "$BIN/ssh"
BACKEND=local
seq_run() { rm -f "$CALLS"; local h=(); [[ "$BACKEND" == ssh ]] && h=(--host far-host)
  SUDO="$BIN/sudo" SSH="$BIN/ssh" AGENT_FABRIC_CLONE_URL="$BARE" HOME="$SANDBOX/home" \
  AGENT_FABRIC_ACCOUNTS_SNAPSHOT="$SANDBOX/persist/snap" AGENT_FABRIC_RC_LOCAL_D="$SANDBOX/persist/rcd" AGENT_FABRIC_ETC="$SANDBOX/persist/etc" AGENT_FABRIC_LOGINCTL="$BIN/loginctl" \
  AGENT_FABRIC_LEASES="$SANDBOX/persist/leases" AGENT_FABRIC_TMPFILES_D="$SANDBOX/persist/tmpfiles.d" \
  bash "$FAB/runtime/provisioning/new-agent.sh" "$@" "${h[@]}" 2>&1; }
cp "$SEQ/enroll.sh" "$FAB/runtime/provisioning/secrets/enroll.sh"
reset_seq() { rm -rf "$HOMES" "$SEQ/passwd" "$SEQ/enrolled" "$FAULT" "$SANDBOX/persist/etc/subuid" "$SANDBOX/persist/etc/subgid"; mkdir -p "$HOMES"; }

for BACKEND in local ssh; do
echo "new-agent: the real sequence on the $BACKEND backend"
: > "$SSHLOG"
reset_seq; out="$(seq_run seq-login backend-dev --project demo)"; rc=$?
[[ $rc -eq 0 ]] && ok "the whole sequence exits 0" || bad "rc=$rc" "$out"
# 5b: the fixture fabric has no store for this login (no tools/fabric/
# secret_store.py answers export-key), so the step is said and skipped,
# never a stop; with a parent store it calls store-enroll.sh for the
# account on its placed host.
grep -q "5b. skipped: this login has no store of its own yet" <<<"$out" && ok "5b without a parent store: said and skipped, the sequence goes on" || bad "5b skip" "$out"
if [[ "$BACKEND" == local ]]; then
  mkdir -p "$FAB/tools/fabric"
  printf '#!/usr/bin/env python3\nimport sys\nsys.exit(0 if sys.argv[1:] == ["export-key"] else 9)\n' > "$FAB/tools/fabric/secret_store.py"
  printf '#!/usr/bin/env bash\necho "store-enroll $*" >> "%s"\n' "$CALLS" > "$FAB/runtime/provisioning/secrets/store-enroll.sh"
  chmod +x "$FAB/runtime/provisioning/secrets/store-enroll.sh"
  reset_seq; out5b="$(seq_run seq-login backend-dev --project demo)"; rc5b=$?
  grep -qx "store-enroll seq-login --host $LOCAL" "$CALLS" && grep -q "5b. its key made and certified" <<<"$out5b" \
    && ok "5b with a parent store: store-enroll.sh for the account on its host" || bad "5b enrol (rc=$rc5b)" "$(cat "$CALLS" 2>/dev/null) $out5b"
  rm -f "$FAB/tools/fabric/secret_store.py" "$FAB/runtime/provisioning/secrets/store-enroll.sh"
  reset_seq; out="$(seq_run seq-login backend-dev --project demo)"; rc=$?   # back to the plain run the next checks read
fi
grep -q "persist-accounts.sh seq-login" "$CALLS" && grep -q "^loginctl enable-linger seq-login" "$CALLS" && ok "the account is persisted: persist-accounts.sh through sudo, linger enabled" || bad "persist step missing" "$(grep -i "persist\|linger" "$CALLS")"
H="$HOMES/seq-login"
[[ -x "$H/.local/bin/claude" && -x "$H/.local/bin/ori" && -d "$H/projects/agent-fabric/.git" && -d "$H/projects/demo/.git" && -d "$H/projects/demo/node_modules" ]] \
  && [[ "$(grep -c "^github.com " "$H/.ssh/known_hosts")" == "$(grep -c . "$ROOT/runtime/provisioning/github-host-keys")" ]] && ! grep -q "^ssh-keyscan" "$CALLS" && grep -q "^enroll fill-from" "$CALLS" && grep -q "^enroll issue-openrouter-keys" "$CALLS" \
  && ok "account, binaries, the published host keys (no keyscan), fabric and project clones, enrolment, toolchain all there" || bad "sequence incomplete" "$out
$(cat "$CALLS")"
[[ "$(ssh-keygen -lf "$H/.ssh/known_hosts" | awk '{print $2, $4}' | tr -d '()' | sort)" == "$(sort "$ROOT/runtime/provisioning/github-host-keys.fingerprints")" ]] \
  && ok "the account's known_hosts carries exactly the committed fingerprints" || bad "known_hosts fingerprints differ from the committed list" "$(ssh-keygen -lf "$H/.ssh/known_hosts")"
grep -q "chown seq-login:staff" "$CALLS" && ok "chown uses the account's primary group, not the login" || bad "chown assumed group == login" "$(grep chown "$CALLS")"
grep -q "^usermod --add-subuids 524288-589823 --add-subgids 524288-589823 seq-login" "$CALLS" && grep -qx "seq-login:524288:65536" "$SANDBOX/persist/etc/subuid" "$SANDBOX/persist/etc/subgid" && ok "a subordinate uid and gid range is allocated for the new account (rootless podman)" || bad "subuid/subgid" "$(grep usermod "$CALLS"; cat "$SANDBOX/persist/etc/subuid" 2>&1)"
grep -q "new-agent: done" <<<"$out" && ok "…and the person's list is printed" || bad "no closing list" "$out"
if [[ "$BACKEND" == ssh ]]; then
  grep -q "new-agent-worker.sh host-check seq-login" "$SSHLOG" && grep -q "new-agent-worker.sh prepare seq-login backend-dev" "$SSHLOG" && grep -q "new-agent-worker.sh finish seq-login backend-dev --clone demo=" "$SSHLOG" \
    && ok "ssh: host-check, prepare and finish each went to the far host's worker" || bad "ssh phases" "$(cat "$SSHLOG")"
  grep -q "^new-agent: host far-host (over ssh)" <<<"$out" && ok "…and the run says so" || bad "no ssh host line" "$out"
  ! grep -q "enroll" "$SSHLOG" && ok "…while enrolment stayed on the coordinator" || bad "enroll went over ssh" "$(cat "$SSHLOG")"
else
  [[ ! -s "$SSHLOG" ]] && ok "local: ssh never called" || bad "ssh called on the local backend" "$(cat "$SSHLOG")"
fi
out="$(seq_run seq-login backend-dev --project demo)"
grep -q "1. account seq-login exists" <<<"$out" && grep -q "2. claude $PIN present" <<<"$out" && grep -q "OpenRouter key: present" <<<"$out" && ! grep -q "^useradd" "$CALLS" && ! grep -q "^usermod --add-subuids" "$CALLS" && grep -q "subuid/subgid: 524288:65536" <<<"$out" \
  && ok "a second run skips every step already true" || bad "not idempotent" "$out"

for fault in useradd "git" "enroll seq-login" "enroll fill-from" curl; do
  reset_seq
  case "$fault" in
    git) printf 'git\n' > "$FAULT" ;;              # the fake git fails a clone
    *) printf '%s\n' "$fault" > "$FAULT" ;;
  esac
  out="$(seq_run seq-login backend-dev --project demo)"; rc=$?
  if [[ $rc -eq 1 ]] && grep -q "step failed" <<<"$out" && ! grep -q "new-agent: done" <<<"$out"; then
    ok "a failed '$fault' stops the script, named, before the closing list"
  else bad "a failed '$fault' did not stop the script (rc=$rc)" "$out"; fi
  case "$fault" in
    useradd) [[ ! -d "$H" ]] && ! grep -q "^curl\|^enroll" "$CALLS" && ok "…and nothing after useradd ran" || bad "steps ran after the failed useradd" "$(cat "$CALLS")" ;;
    curl) ! grep -q "^enroll\|^ssh-keyscan" "$CALLS" && ok "…and nothing after the installer ran" || bad "steps ran after the failed installer" "$(cat "$CALLS")" ;;
    "enroll seq-login") ! grep -q "^enroll fill-from" "$CALLS" && [[ ! -d "$H/projects/demo" ]] && ok "…and no clone, no fill-from after a failed enrolment" || bad "steps ran after the failed enrolment" "$(cat "$CALLS")" ;;
  esac
  rm -f "$FAULT"; out="$(seq_run seq-login backend-dev --project demo)"; rc=$?
  [[ $rc -eq 0 ]] && [[ -d "$H/projects/demo/node_modules" ]] && ok "…and the re-run after '$fault' converges" || bad "re-run after '$fault' did not converge (rc=$rc)" "$out
$(cat "$CALLS")"
done
done

echo
if [[ $FAIL -eq 0 ]]; then echo "test_new-agent: OK — $PASS assertion(s) passed."; else echo "test_new-agent: FAILED — $FAIL assertion(s) failed."; exit 1; fi
