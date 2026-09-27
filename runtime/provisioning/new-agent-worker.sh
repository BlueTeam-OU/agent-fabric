#!/usr/bin/env bash
# runtime/provisioning/new-agent-worker.sh — the host half of new-agent.sh:
# everything that touches THIS machine (the account, its home, the
# installers, the host keys, the clones, bootstrap, the binding, the
# toolchain, the verification), run on the host the account is placed on
# — directly by new-agent.sh for its own host, through
# runtime/hostexec/hostexec for any other. It knows nothing of Doppler or
# the API keys: those are the coordinator's, between its two phases.
#
#   new-agent-worker.sh prepare <login> <role> [--claude VERSION|stable|latest] [--dry-run]
#       steps 0-4: host audit, account, home + claude + ori, GitHub's host keys, the fabric clone
#   new-agent-worker.sh finish <login> <role> [--clone <id>=<remote>]... [--dry-run]
#       steps 6-10: project clones, bootstrap, the role bound, toolchains, verification
#   new-agent-worker.sh host-check <login>
#       what this host reports about itself and the account (hostname -s
#       first, then whether the account exists); needs no sudo
#
# Runs as the host's operator (sudo, no password); as_login runs one
# shell line as the account. Every step is must, probe or best_effort
# (new-agent.sh's failure semantics; test_new-agent.sh injects a failure
# at each must and asserts nothing after it ran).
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
PHASE="${1:-}"; shift || true
LOGIN="${1:-}"; ROLE=""; DRY=0; CLAUDE_TARGET=""; PROJECTS=(); declare -A REMOTE
case "$PHASE" in
    prepare|finish) ROLE="${2:-}"; shift 2 || true ;;
    host-check) shift || true ;;
    *) echo "usage: new-agent-worker.sh prepare|finish <login> <role> ... | host-check <login> [--project <id>]..." >&2; exit 2 ;;
esac
while (( $# )); do
    case "$1" in
        --dry-run) DRY=1 ;;
        --claude) CLAUDE_TARGET="$2"; shift ;;
        --claude=*) CLAUDE_TARGET="${1#--claude=}" ;;
        --clone) pid="${2%%=*}"; REMOTE["$pid"]="${2#*=}"; PROJECTS+=("$pid"); shift ;;
        --clone=*) v="${1#--clone=}"; pid="${v%%=*}"; REMOTE["$pid"]="${v#*=}"; PROJECTS+=("$pid") ;;
        --project) PROJECTS+=("$2"); shift ;;
        *) echo "new-agent-worker: unknown argument $1" >&2; exit 2 ;;
    esac
    shift
done
[[ -n "$LOGIN" ]] || { echo "new-agent-worker: no login" >&2; exit 2; }
[[ "$PHASE" == host-check || -n "$ROLE" ]] || { echo "new-agent-worker: no role" >&2; exit 2; }

say() { printf 'new-agent: %s\n' "$*" >&2; }
die() { printf 'new-agent: %s\n' "$*" >&2; exit 1; }
run() { if (( DRY )); then say "would: $*"; else "$@"; fi; }
must() { run "$@" || die "step failed: $* — nothing after it ran; fix the cause and re-run (every step is idempotent)"; }
probe() { "$@"; }
best_effort() { run "$@" || say "warning: $* failed; continuing"; }
LOG="$(mktemp)"; trap 'rm -f "$LOG"' EXIT
SUDO="${SUDO:-sudo}"   # a test puts a fake here; the real one is sudo
HOME_DIR="$(getent passwd "$LOGIN" 2>/dev/null | cut -d: -f6)"; HOME_DIR="${HOME_DIR:-/home/$LOGIN}"
GROUP="$(id -gn "$LOGIN" 2>/dev/null || echo "$LOGIN")"   # the primary group, whatever the host's policy names it
# One shell line as the account, in a LOGIN shell (the account's profile:
# what its installers put on PATH); `must as_login '…'` when the line must
# succeed. The PATH is re-asserted INSIDE the shell: Debian's /etc/profile
# assigns PATH outright for a non-root login, so what env -i set would be
# gone by the time the line runs (found by the Debian smoke container,
# which then downloaded the real claude in place of the test's fake).
as_login() {  # HOME_DIR is re-derived once the account exists, so the PATH is built per call
    local p="/usr/local/bin:/usr/bin:/bin:$HOME_DIR/.local/bin"
    $SUDO -n -u "$LOGIN" -H env -i HOME="$HOME_DIR" PATH="$p" AGENT_FABRIC_PATH="$p" \
        bash -lc 'export PATH="$AGENT_FABRIC_PATH:$PATH"; cd "$HOME" && eval "$1"' _ "$*"
}
if [[ "$PHASE" == host-check ]]; then
    # The host names itself; the coordinator compares this with the
    # registry id it reached the host as, and never stamps a host it is not on.
    hostname -s
    getent passwd "$LOGIN" >/dev/null && echo "account: present" || echo "account: absent"
    exit 0
fi
(( DRY )) || $SUDO -n true 2>/dev/null || die "sudo without a password is needed for the account steps (the operator on $(hostname -s) has none)."

if [[ "$PHASE" == prepare ]]; then
    # ---- 0. the host ----------------------------------------------------------------
    # The fabric's host contract (platform/detect.sh: FABRIC_HOST_TOOLS) —
    # what its hooks, scripts and provisioning call; the package each comes
    # from, and where a package persists, is the platform profile's. A
    # project's extra needs are its own host-check (finish, below).
    # shellcheck source=runtime/provisioning/platform/detect.sh
    . "$ROOT/runtime/provisioning/platform/detect.sh"
    missing_pkgs=()
    for tool in "${FABRIC_HOST_TOOLS[@]}"; do
        command -v "$tool" >/dev/null 2>&1 || missing_pkgs+=("$(pkg_for "$tool")")
    done
    if (( ${#missing_pkgs[@]} )); then
        mapfile -t missing_pkgs < <(printf '%s\n' "${missing_pkgs[@]}" | sort -u)
        if (( PERSISTS_ACROSS_REBOOT )); then say "0. $PLATFORM_ID: this host lacks ${missing_pkgs[*]}: $PKG_INSTALL_HINT ${missing_pkgs[*]}"
        else say "0. $PLATFORM_ID: this AppVM lacks ${missing_pkgs[*]} — a package does not survive a reboot here;"
             say "   $PKG_INSTALL_HINT ${missing_pkgs[*]}   (then restart this AppVM)"; fi
    else say "0. $PLATFORM_ID: host tools present (${#FABRIC_HOST_TOOLS[@]}, the fabric's contract)"; fi
    # doppler: a static binary; /usr/local persists in an AppVM, and enroll.sh
    # reads it from there for every account.
    if [[ -x /usr/local/bin/doppler ]]; then say "   doppler: /usr/local/bin/doppler"
    elif command -v doppler >/dev/null 2>&1; then
        best_effort $SUDO -n install -m 755 "$(command -v doppler)" /usr/local/bin/doppler; say "   doppler: copied to /usr/local/bin (persistent)"
    else
        if (( DRY )); then say "would: install doppler to /usr/local/bin with its vendor script (curl -Ls https://cli.doppler.com/install.sh | sudo sh)"
        else curl -Ls -m 60 https://cli.doppler.com/install.sh | $SUDO -n sh >/dev/null 2>&1 && say "   doppler: installed to /usr/local/bin" || say "   warning: doppler NOT installed (vendor script failed); step 5 will stop there"; fi
    fi


    # ---- 1. the account ---------------------------------------------------------
    if getent passwd "$LOGIN" >/dev/null; then say "1. account $LOGIN exists"
    else must $SUDO -n useradd -m -s /bin/bash -c "agent-fabric $ROLE" "$LOGIN"; say "1. account $LOGIN created"; fi
    HOME_DIR="$(getent passwd "$LOGIN" | cut -d: -f6)"; HOME_DIR="${HOME_DIR:-/home/$LOGIN}"
    # A subordinate uid AND gid range, or rootless podman can unpack no image
    # and every Testcontainers suite fails on the login: useradd allocates one
    # by default (login.defs SUB_UID_COUNT), but an account made another way
    # has none — architect-cto-01 was that account, found 2026-09-19 with
    # 2716 fixture failures. The next free block above every range in the
    # file (SUB_UID_MIN when the file is empty), the same block for both.
    ETC="${AGENT_FABRIC_ETC:-/etc}"
    if grep -qs "^$LOGIN:" "$ETC/subuid" && grep -qs "^$LOGIN:" "$ETC/subgid"; then say "   subuid/subgid: $(grep "^$LOGIN:" "$ETC/subuid" | cut -d: -f2-)"
    else
        sub_min="$(awk '/^SUB_UID_MIN/{print $2}' "$ETC/login.defs" 2>/dev/null)"; sub_min="${sub_min:-524288}"
        sub_count="$(awk '/^SUB_UID_COUNT/{print $2}' "$ETC/login.defs" 2>/dev/null)"; sub_count="${sub_count:-65536}"
        sub_start="$(cat "$ETC/subuid" "$ETC/subgid" 2>/dev/null | awk -F: -v m="$sub_min" 'BEGIN{e=m} $2+$3>e{e=$2+$3} END{print e}')"
        if (( DRY )); then say "would: usermod --add-subuids $sub_start-$((sub_start + sub_count - 1)) --add-subgids (the same) $LOGIN"
        else must $SUDO -n usermod --add-subuids "$sub_start-$((sub_start + sub_count - 1))" --add-subgids "$sub_start-$((sub_start + sub_count - 1))" "$LOGIN"; say "   subuid/subgid: $sub_start:$sub_count allocated (rootless podman needs both)"; fi
    fi
    # The account's primary group, whatever the host's policy names it (not
    # necessarily the login: user-private groups are a distribution choice).
    GROUP="$(id -gn "$LOGIN" 2>/dev/null || echo "$LOGIN")"
    must $SUDO -n chmod 700 "$HOME_DIR"
    if probe getent group otscache >/dev/null && ! id -nG "$LOGIN" 2>/dev/null | tr ' ' '\n' | grep -qx otscache; then
        best_effort $SUDO -n usermod -aG otscache "$LOGIN"; say "   otscache (the shared timestamp cache): joined"; fi
    # The account must survive this host's reboot: linger on every platform
    # (its user manager, and the control agent under it, run without a
    # login); on a Qubes AppVM the record itself is volatile and goes into
    # the /rw snapshot the boot script re-adds (persist-accounts.sh) —
    # after the group join above, so the membership is in the snapshot.
    must $SUDO -n bash "$ROOT/runtime/provisioning/persist-accounts.sh" "$LOGIN"; say "   persisted across reboot (linger$( (( PERSISTS_ACROSS_REBOOT )) || printf '; record snapshot under /rw' ))"


    # ---- 2. the home skeleton and the two binaries ----------------------------
    must $SUDO -n -u "$LOGIN" mkdir -p "$HOME_DIR"/{projects,.ssh,.claude,.config/gh,.local/bin,.local/share/claude/versions}
    must $SUDO -n -u "$LOGIN" chmod 700 "$HOME_DIR/.ssh"
    must $SUDO -n chown "$LOGIN:$GROUP" "$HOME_DIR/.local" "$HOME_DIR/.local/bin" "$HOME_DIR/.local/share"
    # claude: the vendor's installer, as the account, on the version the
    # fleet pins (runtime/claude-code/harness.json — what `fabric-ctl …
    # upgrade claude` brings every account to), so a new account starts
    # where the others are; --claude overrides it (a version, stable or
    # latest), and with no pin readable it is the vendor's latest, resolved
    # against the release pointer. Its layout is the one this script and the
    # runbook assume: ~/.local/bin/claude -> ~/.local/share/claude/versions/<v>.
    pinned="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("claude") or "")' "$ROOT/runtime/claude-code/harness.json" 2>/dev/null || true)"
    # The pin reaches as_login's eval below: a pin that is not a version is
    # refused, and a pin that cannot be read is said, never silently turned
    # into latest. (--claude is checked by new-agent.sh and again below.)
    if [[ -n "$pinned" && ! "$pinned" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        die "runtime/claude-code/harness.json pins claude '$pinned', which is not a version; nothing installed"
    fi
    [[ -n "${CLAUDE_TARGET:-}" || -n "$pinned" ]] || say "   claude: no readable pin in runtime/claude-code/harness.json — the vendor's latest instead"
    want="${CLAUDE_TARGET:-${pinned:-latest}}"
    # Checked again here, whatever the caller checked: this value is spliced
    # into the string as_login evals.
    [[ "$want" =~ ^(stable|latest|[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?)$ ]] || die "claude target '$want' is not stable, latest or a version; nothing installed"
    resolved="$want"
    if [[ "$want" == latest ]]; then
        resolved="$(curl -fsSL -m 20 https://downloads.claude.ai/claude-code-releases/latest 2>/dev/null | tr -d '[:space:]')"
        [[ "$resolved" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]] || resolved=""
    fi
    have="$(as_login 'test -e ~/.local/bin/claude && readlink -f ~/.local/bin/claude | xargs -r basename' 2>/dev/null || true)"
    if [[ -n "$have" && -n "$resolved" && "$have" == "$resolved" ]]; then say "2. claude $have present (= $want)"
    else
        if (( DRY )); then say "would: as $LOGIN: curl -fsSL https://claude.ai/install.sh | bash -s -- $want"
        else
            as_login "curl -fsSL --proto '=https' -m 120 https://claude.ai/install.sh | bash -s -- '$want'" >"$LOG" 2>&1 \
                && as_login "claude --version" >/dev/null 2>&1 \
                || { tail -5 "$LOG" >&2; die "step failed: claude — the vendor's installer failed for $LOGIN (target $want); nothing after it ran"; }
            say "2. claude $(as_login 'claude --version' | cut -d' ' -f1) installed by the vendor's installer ($want${have:+, was $have})"
        fi
    fi
    # ori: the vendor's installer (stable channel; no version pin exists), into
    # ~/.local/bin as it does by default.
    if as_login "test -x ~/.local/bin/ori" 2>/dev/null; then say "   ori $(as_login 'ori --version 2>/dev/null | head -1' | tr -d '\n' | cut -c1-24) present"
    else
        if (( DRY )); then say "would: as $LOGIN: curl -fsSL https://openrouter.ai/labs/ori/install.sh | bash"
        else
            as_login "curl -fsSL --proto '=https' -m 120 https://openrouter.ai/labs/ori/install.sh | bash" >"$LOG" 2>&1 \
                && as_login "test -x ~/.local/bin/ori" \
                || { tail -5 "$LOG" >&2; die "step failed: ori — the vendor's installer failed for $LOGIN; nothing after it ran"; }
            say "   ori installed by the vendor's installer"
        fi
    fi


    # ---- 3. GitHub's host keys --------------------------------------------------
    # From the committed copy of GitHub's PUBLISHED keys (github-host-keys,
    # api.github.com/meta, fingerprints checked against docs.github.com when
    # the file was written — docs/live-checks/2026-09-16-github-host-keys.md),
    # never ssh-keyscan: a scan trusts whatever answers on the network the
    # bootstrap is about to use (review, 2026-09-16). Every key line the
    # account does not hold yet is appended; a changed key at GitHub is a
    # change to the committed file, reviewed like any other.
    HOST_KEYS="$ROOT/runtime/provisioning/github-host-keys"
    [[ -s "$HOST_KEYS" ]] || die "step failed: $HOST_KEYS is missing or empty; nothing after it ran"
    missing_keys="$(while IFS= read -r line; do [[ -n "$line" ]] && ! $SUDO -n grep -qsxF "$line" "$HOME_DIR/.ssh/known_hosts" 2>/dev/null && printf '%s\n' "$line"; done < "$HOST_KEYS")"
    if [[ -z "$missing_keys" ]]; then say "3. github.com host keys trusted ($(grep -c . "$HOST_KEYS") published keys)"
    else
        if (( DRY )); then say "would: append GitHub's published host keys (runtime/provisioning/github-host-keys) to $HOME_DIR/.ssh/known_hosts"
        else must bash -c 'printf "%s\n" "$1" | '"$SUDO"' -n -u "$2" tee -a "$3/.ssh/known_hosts" >/dev/null' _ "$missing_keys" "$LOGIN" "$HOME_DIR"
             must $SUDO -n -u "$LOGIN" chmod 600 "$HOME_DIR/.ssh/known_hosts"; say "3. github.com host keys trusted (from the committed published set)"; fi
    fi


    # ---- 4. the fabric checkout -------------------------------------------------
    if $SUDO -n test -d "$HOME_DIR/projects/agent-fabric/.git"; then say "4. ~/projects/agent-fabric present"
    else must as_login "git clone -q '${AGENT_FABRIC_CLONE_URL:-https://github.com/gzapi-org/agent-fabric.git}' ~/projects/agent-fabric"; say "4. agent-fabric cloned (https; the fabric is public)"; fi

    exit 0
fi

# ---- finish: after the coordinator's Doppler steps --------------------------
# What a project needs of the host beyond the fabric's contract is the
# project's to say: projects/<id>/integration/provisioning/host-check.sh,
# run here for each project, names what is missing for the person.
for pid in "${PROJECTS[@]+"${PROJECTS[@]}"}"; do
    hc="$ROOT/projects/$pid/integration/provisioning/host-check.sh"
    [[ -x "$hc" ]] && { probe bash "$hc" 2>&1 | sed 's/^/   /' >&2; }
done
# ---- 6. the project clones, as the account, over SSH -----------------------
for pid in "${PROJECTS[@]+"${PROJECTS[@]}"}"; do
    if $SUDO -n test -d "$HOME_DIR/projects/$pid/.git"; then say "6. ~/projects/$pid present"
    else must as_login "git clone -q '${REMOTE[$pid]}' ~/projects/'$pid'"; say "6. $pid cloned from ${REMOTE[$pid]}"; fi
done


# ---- 7. bootstrap; 8. the role ------------------------------------------------
if (( DRY )); then say "would: as $LOGIN: bootstrap.sh"
else
    as_login "~/projects/agent-fabric/runtime/claude-code/bootstrap.sh" >"$LOG" 2>&1 || { tail -5 "$LOG" >&2; die "step failed: bootstrap.sh as $LOGIN; nothing after it ran"; }
    tail -1 "$LOG" | sed 's/^/   /' >&2
fi
say "7. bootstrap run"
bound="$(as_login "~/projects/agent-fabric/bin/fabric-role status 2>/dev/null | awk '/^role/{print \$2}'" 2>/dev/null || true)"
if [[ "$bound" == "$ROLE" ]]; then say "8. role $ROLE already bound"
else
    first="${PROJECTS[0]:-}"; where="~/projects${first:+/$first}"
    if (( DRY )); then say "would: as_login cd $where && bin/fabric-role bind '$ROLE'"
    else
        as_login "cd $where && ~/projects/agent-fabric/bin/fabric-role bind '$ROLE'" >"$LOG" 2>&1 || { tail -5 "$LOG" >&2; die "step failed: fabric-role bind $ROLE as $LOGIN; nothing after it ran"; }
        grep -i "bound\|refus" "$LOG" | sed 's/^/   /' >&2
    fi
    say "8. role $ROLE bound (from $where)"; fi


# ---- 9. the toolchain each project declares ----------------------------------
for pid in "${PROJECTS[@]+"${PROJECTS[@]}"}"; do
    wc="$HOME_DIR/projects/$pid"
    if probe $SUDO -n test -f "$wc/pnpm-lock.yaml"; then
        probe as_login "command -v pnpm >/dev/null" || { must as_login "npm config set prefix ~/.local && npm i -g pnpm >/dev/null"; say "9. pnpm installed under ~/.local"; }
        probe $SUDO -n test -d "$wc/node_modules" && say "9. $pid: node_modules present" || { must as_login "cd ~/projects/'$pid' && pnpm install --frozen-lockfile >/dev/null 2>&1"; say "9. $pid: pnpm install"; }
    elif probe $SUDO -n test -f "$wc/package-lock.json"; then
        probe $SUDO -n test -d "$wc/node_modules" && say "9. $pid: node_modules present" || { must as_login "cd ~/projects/'$pid' && npm ci >/dev/null 2>&1"; say "9. $pid: npm ci"; }
    elif probe $SUDO -n test -f "$wc/requirements.txt"; then
        probe $SUDO -n test -d "$wc/.venv" && say "9. $pid: .venv present" || { must as_login "cd ~/projects/'$pid' && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt"; say "9. $pid: venv"; }
    fi
done


# ---- 10. verify, and what is left for a person --------------------------------
(( DRY )) && { say "dry run: nothing verified"; exit 0; }
say "10. verification"
as_login "~/projects/agent-fabric/bin/fabric-secrets status 2>&1 | grep -E 'missing|OK|NOT OK'" | sed 's/^/   /' >&2
as_login "gh auth status 2>&1 | grep -o 'Logged in.*' | head -1" | sed 's/^/   gh: /' >&2
for pid in "${PROJECTS[@]+"${PROJECTS[@]}"}"; do
    as_login "timeout 20 git -C ~/projects/'$pid' ls-remote --heads origin >/dev/null 2>&1 && echo 'ssh to origin: ok' || echo 'ssh to origin: FAILED'" | sed "s/^/   $pid /" >&2
done
as_login "printf 'git: %s <%s> signingkey=%s gpgsign=%s\n' \"\$(git config --global user.name)\" \"\$(git config --global user.email)\" \"\$(git config --global user.signingkey | cut -c1-12)\" \"\$(git config --global commit.gpgsign)\"" | sed 's/^/   /' >&2
gpgkeys="$(as_login "gpg --list-secret-keys 2>/dev/null | grep -c ^sec; true" 2>/dev/null | tr -dc 0-9 | head -c 4)"; gpgkeys="${gpgkeys:-0}"
first="${PROJECTS[0]:-}"; where="~/projects${first:+/$first}"
for prov in anthropic openrouter; do
    as_login "cd $where && ~/projects/agent-fabric/runtime/openrouter/launch --provider $prov --print 2>&1 | grep -E '^launch:|resolved profile' | head -1" | sed "s/^/   launch ($prov): /" >&2
done
# The control agent bootstrap enabled in the account's user manager answers
# the coordinator from here on: one ping, from this checkout, as the operator.
"$ROOT/bin/fabric-ctl" "$LOGIN" ping 2>&1 | tail -n +2 | sed 's/^/   control plane: /' >&2 || true
# A Claude account for plain claude: a template reference synced into the
# login's secrets.env (docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md) — the launcher starts no
# plain-claude session without one. Never a copy of another login's
# .credentials.json: a refresh token has one holder, and the first renewal
# by either signs the other out.
creds="$($SUDO -n grep -q '^export CLAUDE_CODE_OAUTH_TOKEN=' "$HOME_DIR/.config/agent-fabric/secrets.env" 2>/dev/null && echo template || echo no)"
cat >&2 <<EOF
new-agent: done. Left for a person, in a terminal (nothing here can do them):
   $( [[ "$gpgkeys" -gt 0 ]] && echo "- GPG secret key: present" || echo "- GPG secret key: NONE — commits will fail to sign. As the coordinator, in a terminal (the key has a passphrase):
       gpg --export-secret-keys \"\$(git config --get user.signingkey)\" | sudo -u $LOGIN gpg --batch --import
       sudo -u $LOGIN bash -c \"echo '\$(git config --get user.signingkey):6:' | gpg --import-ownertrust\"" )
   $( case "$creds" in
        template) echo "- Claude account: a template token (plain-claude path ready)" ;;
        *) echo "- Claude account: no template token — the launcher refuses a plain-claude session (--provider anthropic) without one, its own /login included; the broker path does not need one.
       As the coordinator: bin/fabric-accounts assign $LOGIN <account> (docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md). Never copy another login's .credentials.json." ;;
      esac )
   - first launch is interactive, to accept the workspace-trust dialog:
       moveto $LOGIN${first:+ $first}   then   runtime/openrouter/launch
EOF

