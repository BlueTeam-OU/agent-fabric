#!/usr/bin/env bash
# runtime/provisioning/new-agent-worker.sh — the host half of new-agent.sh:
# what touches THIS machine (the account, its home, the installers, the
# host keys, the clones, bootstrap, the binding, the toolchain), run on the
# host the account is placed on, through runtime/hostexec/hostexec; it
# knows nothing of the account's secrets (ADR-038). A step-runner (ADR-040
# rule 1): sudo, useradd and the installers here; its decisions, and why,
# in tools/fabric/new_agent_worker.py, run by the pinned Python's fixed path.
#   new-agent-worker.sh prepare <login> <role> [--claude V] [--dry-run]   0-4
#   new-agent-worker.sh finish <login> <role> [--clone <id>=<remote>]... [--dry-run]   6-10
#   new-agent-worker.sh host-check <login>   hostname -s, then whether the account exists
# Every step is must, probe or best_effort (test_new-agent.sh fails each must).
set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
PY=/usr/local/bin/fabric-python; W="$ROOT/tools/fabric/new_agent_worker.py"
[[ -x "$PY" ]] || { echo "new-agent: the fleet's pinned Python is not installed at $PY on $(hostname -s); as root: /usr/bin/python3 $ROOT/tools/fabric/python_pin.py install" >&2; exit 127; }
vars="$("$PY" -I "$W" args "$@")" || exit $?
eval "$vars"
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
# One shell line as the account, in a login shell; why the PATH is set twice: new_agent_worker.Account.
as_login() {
    local p="/usr/local/bin:/usr/bin:/bin:$HOME_DIR/.local/bin"
    $SUDO -n -u "$LOGIN" -H env -i HOME="$HOME_DIR" PATH="$p" AGENT_FABRIC_PATH="$p" \
        bash -lc 'export PATH="$AGENT_FABRIC_PATH:$PATH"; cd "$HOME" && eval "$1"' _ "$*"
}
[[ "$PHASE" == host-check ]] && { "$PY" -I "$W" host-check "$LOGIN"; exit $?; }   # not exec: the EXIT trap removes $LOG
(( DRY )) || $SUDO -n true 2>/dev/null || die "sudo without a password is needed for the account steps (the operator on $(hostname -s) has none)."
if [[ "$PHASE" == prepare ]]; then
    # ---- 0. the host: the fabric's contract (platform/detect.sh), each missing tool's package
    # shellcheck source=runtime/provisioning/platform/detect.sh
    . "$ROOT/runtime/provisioning/platform/detect.sh"
    missing_pkgs=()
    for tool in "${FABRIC_HOST_TOOLS[@]}"; do command -v "$tool" >/dev/null 2>&1 || missing_pkgs+=("$(pkg_for "$tool")"); done
    (( ${#missing_pkgs[@]} )) && mapfile -t missing_pkgs < <(printf '%s\n' "${missing_pkgs[@]}" | sort -u)
    "$PY" -I "$W" audit "$PLATFORM_ID" "$PERSISTS_ACROSS_REBOOT" "$PKG_INSTALL_HINT" "${#FABRIC_HOST_TOOLS[@]}" "${missing_pkgs[@]+"${missing_pkgs[@]}"}"
    # ---- 1. the account, its subordinate ids, home 700, the shared cache, linger
    if getent passwd "$LOGIN" >/dev/null; then say "1. account $LOGIN exists"
    else must $SUDO -n useradd -m -s /bin/bash -c "agent-fabric $ROLE" "$LOGIN"; say "1. account $LOGIN created"; fi
    HOME_DIR="$(getent passwd "$LOGIN" | cut -d: -f6)"; HOME_DIR="${HOME_DIR:-/home/$LOGIN}"
    plan="$("$PY" -I "$W" subids "$LOGIN" "${AGENT_FABRIC_ETC:-/etc}")" || die "the subordinate id plan for $LOGIN could not be made"
    case "$plan" in
        have\ *) say "   subuid/subgid: ${plan#have }" ;;
        alloc\ *) r="${plan#alloc }"
            if (( DRY )); then say "would: usermod --add-subuids $r --add-subgids (the same) $LOGIN"
            else must $SUDO -n usermod --add-subuids "$r" --add-subgids "$r" "$LOGIN"; say "   subuid/subgid: ${r%-*}:$(( ${r#*-} - ${r%-*} + 1 )) allocated (rootless podman needs both)"; fi ;;
    esac
    GROUP="$(id -gn "$LOGIN" 2>/dev/null || echo "$LOGIN")"
    must $SUDO -n chmod 700 "$HOME_DIR"
    if probe getent group otscache >/dev/null && ! id -nG "$LOGIN" 2>/dev/null | tr ' ' '\n' | grep -qx otscache; then
        best_effort $SUDO -n usermod -aG otscache "$LOGIN"; say "   otscache (the shared timestamp cache): joined"; fi
    # Survive the host's reboot: linger everywhere; on Qubes the record goes into the /rw snapshot (after the group join).
    must $SUDO -n bash "$ROOT/runtime/provisioning/persist-accounts.sh" "$LOGIN"; say "   persisted across reboot (linger$( (( PERSISTS_ACROSS_REBOOT )) || printf '; record snapshot under /rw' ))"
    # ---- 2. the home skeleton, then claude and ori from their vendors' installers, as the account
    must $SUDO -n -u "$LOGIN" mkdir -p "$HOME_DIR"/{projects,.ssh,.claude,.config/gh,.local/bin,.local/share/claude/versions}
    must $SUDO -n -u "$LOGIN" chmod 700 "$HOME_DIR/.ssh"
    must $SUDO -n chown "$LOGIN:$GROUP" "$HOME_DIR/.local" "$HOME_DIR/.local/bin" "$HOME_DIR/.local/share"
    want="$("$PY" -I "$W" claude-want "$ROOT" "$CLAUDE_TARGET")" || exit 1
    resolved="$want"
    if [[ "$want" == latest ]]; then
        resolved="$(curl -fsSL -m 20 https://downloads.claude.ai/claude-code-releases/latest 2>/dev/null | tr -d '[:space:]')"
        [[ "$resolved" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]] || resolved=""
    fi
    have="$(as_login 'test -e ~/.local/bin/claude && readlink -f ~/.local/bin/claude | xargs -r basename' 2>/dev/null || true)"
    if [[ -n "$have" && -n "$resolved" && "$have" == "$resolved" ]]; then say "2. claude $have present (= $want)"
    elif (( DRY )); then say "would: as $LOGIN: curl -fsSL https://claude.ai/install.sh | bash -s -- $want"
    else
        as_login "curl -fsSL --proto '=https' -m 120 https://claude.ai/install.sh | bash -s -- '$want'" >"$LOG" 2>&1 \
            && as_login "claude --version" >/dev/null 2>&1 \
            || { tail -5 "$LOG" >&2; die "step failed: claude — the vendor's installer failed for $LOGIN (target $want); nothing after it ran"; }
        say "2. claude $(as_login 'claude --version' | cut -d' ' -f1) installed by the vendor's installer ($want${have:+, was $have})"
    fi
    if as_login "test -x ~/.local/bin/ori" 2>/dev/null; then say "   ori $(as_login 'ori --version 2>/dev/null | head -1' | tr -d '\n' | cut -c1-24) present"
    elif (( DRY )); then say "would: as $LOGIN: curl -fsSL https://openrouter.ai/labs/ori/install.sh | bash"
    else
        as_login "curl -fsSL --proto '=https' -m 120 https://openrouter.ai/labs/ori/install.sh | bash" >"$LOG" 2>&1 \
            && as_login "test -x ~/.local/bin/ori" \
            || { tail -5 "$LOG" >&2; die "step failed: ori — the vendor's installer failed for $LOGIN; nothing after it ran"; }
        say "   ori installed by the vendor's installer"
    fi
    # ---- 3. GitHub's published host keys, never a keyscan; 4. the fabric checkout
    HOST_KEYS="$ROOT/runtime/provisioning/github-host-keys"
    [[ -s "$HOST_KEYS" ]] || die "step failed: $HOST_KEYS is missing or empty; nothing after it ran"
    # A known_hosts not there yet (a new account) holds no key: every published one is missing.
    missing_keys="$({ $SUDO -n cat "$HOME_DIR/.ssh/known_hosts" 2>/dev/null || true; } | "$PY" -I "$W" missing-keys "$HOST_KEYS")" \
        || die "step failed: the host keys $LOGIN lacks could not be read; nothing after it ran"
    if [[ -z "$missing_keys" ]]; then say "3. github.com host keys trusted ($(grep -c . "$HOST_KEYS") published keys)"
    elif (( DRY )); then say "would: append GitHub's published host keys (runtime/provisioning/github-host-keys) to $HOME_DIR/.ssh/known_hosts"
    else must bash -c 'printf "%s\n" "$1" | '"$SUDO"' -n -u "$2" tee -a "$3/.ssh/known_hosts" >/dev/null' _ "$missing_keys" "$LOGIN" "$HOME_DIR"
         must $SUDO -n -u "$LOGIN" chmod 600 "$HOME_DIR/.ssh/known_hosts"; say "3. github.com host keys trusted (from the committed published set)"; fi
    # A clone already there is brought to origin/main, never left old (bootstrap and the launcher run from it), or refused off main.
    if ! $SUDO -n test -d "$HOME_DIR/projects/agent-fabric/.git"; then
        must as_login "git clone -q '${AGENT_FABRIC_CLONE_URL:-https://github.com/gzapi-org/agent-fabric.git}' ~/projects/agent-fabric"; say "4. agent-fabric cloned (https; the fabric is public)"
    else
        branch="$(as_login 'git -C ~/projects/agent-fabric symbolic-ref -q --short HEAD' 2>/dev/null)"
        [[ "$branch" == main ]] || die "step failed: ~/projects/agent-fabric is on ${branch:-a detached HEAD}, not main; bring it to main as $LOGIN, then re-run; nothing after it ran"
        must as_login "timeout 60 git -C ~/projects/agent-fabric pull -q --ff-only origin main"; (( DRY )) || say "4. ~/projects/agent-fabric at origin/main ($(as_login 'git -C ~/projects/agent-fabric rev-parse --short HEAD'))"
    fi
    exit 0
fi
# ---- finish: each project's own host-check, then 6. its clone, as the account, over SSH
for pid in "${PROJECTS[@]+"${PROJECTS[@]}"}"; do
    hc="$ROOT/projects/$pid/integration/provisioning/host-check.sh"
    [[ -x "$hc" ]] && { probe bash "$hc" 2>&1 | sed 's/^/   /' >&2; }
done
for pid in "${PROJECTS[@]+"${PROJECTS[@]}"}"; do
    if $SUDO -n test -d "$HOME_DIR/projects/$pid/.git"; then say "6. ~/projects/$pid present"
    else must as_login "git clone -q '${REMOTE[$pid]}' ~/projects/'$pid'"; say "6. $pid cloned from ${REMOTE[$pid]}"; fi
done
# ---- 7. bootstrap; 8. the role, bound from the first clone
if (( DRY )); then say "would: as $LOGIN: bootstrap.sh"
else
    as_login "~/projects/agent-fabric/runtime/claude-code/bootstrap.sh" >"$LOG" 2>&1 || { tail -5 "$LOG" >&2; die "step failed: bootstrap.sh as $LOGIN; nothing after it ran"; }
    tail -1 "$LOG" | sed 's/^/   /' >&2
fi
say "7. bootstrap run"
first="${PROJECTS[0]:-}"; where="~/projects${first:+/$first}"
bound="$(as_login "~/projects/agent-fabric/bin/fabric-role status 2>/dev/null | awk '/^role/{print \$2}'" 2>/dev/null || true)"
if [[ "$bound" == "$ROLE" ]]; then say "8. role $ROLE already bound"
else
    if (( DRY )); then say "would: as_login cd $where && bin/fabric-role bind '$ROLE'"
    else
        as_login "cd $where && ~/projects/agent-fabric/bin/fabric-role bind '$ROLE'" >"$LOG" 2>&1 || { tail -5 "$LOG" >&2; die "step failed: fabric-role bind $ROLE as $LOGIN; nothing after it ran"; }
        grep -i "bound\|refus" "$LOG" | sed 's/^/   /' >&2
    fi
    say "8. role $ROLE bound (from $where)"; fi
# ---- 9. the toolchain each project declares, from its lockfile
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
# ---- 10. verify, and what is left for a person
(( DRY )) && { say "dry run: nothing verified"; exit 0; }
say "10. verification"
"$PY" -I "$W" verify "$ROOT" "$LOGIN" "$HOME_DIR" "$SUDO" "${PROJECTS[@]+"${PROJECTS[@]}"}"
