#!/usr/bin/env bash
# The operator's ssh into every account on this host (agent-fabric ADR-048).
# Run as root in the AppVM, by the owner; idempotent; --dry-run prints every
# change and makes none (and needs no root):
#
#     sudo runtime/provisioning/platform/qubes/ssh-operator.sh [--dry-run] <operator-key.pub>
#
# Two phases, because on Qubes openssh-server arrives only with the restart
# that follows ssh-template.sh in the TemplateVM, and that restart is the test:
#   1. now, sshd installed or not: stage everything under
#      /rw/config/agent-fabric-ssh/ (root-only, persists) — the drop-in, one
#      authorized_keys file per placed login, this AppVM's host keys (made
#      once, never regenerated), enter-ssh with its conf, and restore.sh —
#      install enter-ssh root-owned in /usr/local/libexec/agent-fabric/ (on
#      Qubes /usr/local persists, in /rw/usrlocal) and the boot block in
#      /rw/config/rc.local; when sshd is already here, apply it now too;
#   2. at every boot the block runs restore.sh: /etc/ssh from the staging
#      copy, `sshd -t`, then sshd.
# On a platform whose /etc persists there is no boot block: phase 2 runs now.
# The operator key is the owner's, made as `user` beforehand (printed at the
# end); this script never generates or reads a private key.
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
fabric="$(cd "$here/../../../.." && pwd)"
S="${AGENT_FABRIC_SSH_STAGE:-/rw/config/agent-fabric-ssh}"
RC_LOCAL="${AGENT_FABRIC_RC_LOCAL:-/rw/config/rc.local}"
REGISTRY="${AGENT_FABRIC_HOSTS_REGISTRY:-$fabric/runtime/hosts/registry.json}"
host="${AGENT_FABRIC_SSH_HOST:-$(hostname -s)}"
LIBEXEC="${AGENT_FABRIC_SSH_LIBEXEC:-/usr/local/libexec/agent-fabric}"
ENTER="${AGENT_FABRIC_MOVETO_ENTER:-/usr/local/share/moveto/enter}"

dry=0
if [[ "${1:-}" == --dry-run ]]; then dry=1; shift; fi
[[ $# -eq 1 ]] || { echo "usage: ssh-operator.sh [--dry-run] <operator-key.pub>" >&2; exit 2; }
pub="$1"
if (( !dry )) && [[ $EUID -ne 0 ]]; then echo "ssh-operator.sh: run as root (sudo); --dry-run needs none" >&2; exit 1; fi
# The forced command runs moveto's root-owned installed enter, never a
# checkout's, which its account could rewrite (ADR-048 §4).
[[ -x "$ENTER" ]] || { echo "ssh-operator.sh: no $ENTER; install moveto first (runtime/provisioning/moveto/install.sh)" >&2; exit 1; }

# One key, `<type> <base64> [comment]`, no options of its own: the options
# are ours (command=…,restrict,pty), and a pasted line carrying its own would
# put two option lists on one key.
read -r -a key < "$pub" || true
[[ $(grep -c . "$pub") -eq 1 && "${key[0]:-}" =~ ^(ssh-ed25519|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh.com)$ \
   && "${key[1]:-}" =~ ^AAAA[A-Za-z0-9+/]+=*$ ]] \
    || { echo "ssh-operator.sh: $pub is not one ed25519 or ecdsa public key line" >&2; exit 1; }
opkey="${key[0]} ${key[1]}"

# The placed logins of this host, from the registry: AllowUsers names them
# and nobody else, and each gets its keys file.
mapfile -t logins < <(python3 -I -c 'import json,sys
r = json.load(open(sys.argv[1]))
print("\n".join(sorted(l for l, h in r["placement"].items() if h == sys.argv[2])))' "$REGISTRY" "$host")
(( ${#logins[@]} )) || { echo "ssh-operator.sh: the registry places no login on $host" >&2; exit 1; }

source "$fabric/runtime/provisioning/platform/detect.sh"
qubes=0; [[ "$PLATFORM" == *-qubes ]] && qubes=1

run() { if (( dry )); then printf 'would run:'; printf ' %q' "$@"; echo; else "$@"; fi; }
# put <mode> <path>: stdin into <path>, root-owned, replaced atomically.
put() {
    if (( dry )); then echo "would write $2 ($1):"; sed 's/^/    /'; return; fi
    local tmp; tmp="$(mktemp "$2.XXXXXX")"; cat > "$tmp"
    chown root:root "$tmp"; chmod "$1" "$tmp"; mv -f "$tmp" "$2"
}

run install -d -m 0700 -o root -g root "$S" "$S/host_keys"
run install -d -m 0755 -o root -g root "$S/authorized_keys"

# Settings sshd takes from the first file that sets them, and Fedora's
# sshd_config includes sshd_config.d/*.conf first, in name order: 50-agent-
# fabric sorts before 50-redhat (which turns X11 forwarding on), so ours win.
put 0600 "$S/50-agent-fabric.conf" <<EOF
# agent-fabric ADR-048, written by ssh-operator.sh; edit there, not here.
ListenAddress 127.0.0.1
PubkeyAuthentication yes
AuthenticationMethods publickey
PasswordAuthentication no
KbdInteractiveAuthentication no
GSSAPIAuthentication no
PermitRootLogin no
DisableForwarding yes
AllowTcpForwarding no
AllowStreamLocalForwarding no
AllowAgentForwarding no
X11Forwarding no
PermitTunnel no
GatewayPorts no
PermitUserEnvironment no
PermitUserRC no
AuthorizedKeysFile /etc/ssh/authorized_keys/%u
AllowUsers ${logins[*]}
EOF

# Every login's forced command is the one root-owned enter-ssh (ADR-048 §4).
for login in "${logins[@]}"; do
    getent passwd "$login" >/dev/null || { echo "ssh-operator.sh: $login is placed here but has no account; no keys file" >&2; continue; }
    put 0644 "$S/authorized_keys/$login" <<<"command=\"$LIBEXEC/enter-ssh\",restrict $opkey"
done
for f in "$S/authorized_keys"/*; do
    [[ -e "$f" ]] || continue
    [[ " ${logins[*]} " == *" ${f##*/} "* ]] || run rm -f -- "$f"
done

# Host keys: made once, here, and restored at every boot, so the registry's
# pin holds. All three types Fedora's sshd-keygen would otherwise create at
# each start of sshd (it fills any missing type, and /etc is fresh at every
# boot), which would offer a new, unpinned key every time. On Qubes never
# adopt /etc's keys: they may be the template's, shared by its AppVMs.
for t in ed25519 ecdsa rsa; do
    k="$S/host_keys/ssh_host_${t}_key"
    [[ -f "$k" ]] && continue
    if (( !qubes )) && [[ -f "/etc/ssh/ssh_host_${t}_key" ]]; then
        run cp -p "/etc/ssh/ssh_host_${t}_key" "/etc/ssh/ssh_host_${t}_key.pub" "$S/host_keys/"
    else
        run ssh-keygen -q -N '' -C "$host" -t "$t" -f "$k"
    fi
done
run install -m 0755 -o root -g root "$here/ssh-restore.sh" "$S/restore.sh"
# Staged, then installed into $LIBEXEC by restore.sh, which runs now and at
# every boot, sshd or not, and puts it back whenever /usr/local's copy differs.
run install -m 0755 -o root -g root "$fabric/runtime/provisioning/moveto/enter-ssh" "$S/enter-ssh"
put 0644 "$S/enter-ssh.conf" <<<"$ENTER"

sshd_here=0; command -v sshd >/dev/null 2>&1 || [[ -x /usr/sbin/sshd ]] && sshd_here=1
if (( qubes )); then
    # One marked block, replaced whole on every run; rc.local made if absent.
    begin="# BEGIN agent-fabric-ssh (ADR-048)"; end="# END agent-fabric-ssh"
    { if [[ -f "$RC_LOCAL" ]]; then sed "/^$begin\$/,/^$end\$/d" "$RC_LOCAL"; else echo '#!/bin/sh'; fi
      printf '%s\n%s\n%s\n' "$begin" "[ -x $S/restore.sh ] && $S/restore.sh" "$end"; } | put 0755 "$RC_LOCAL"
fi
(( sshd_here || qubes )) || { echo "ssh-operator.sh: sshd is not installed; install openssh-server, then re-run" >&2; exit 1; }
run "$S/restore.sh"
echo
echo "Pin these in runtime/hosts/registry.json, hosts.$host.sshd (the coordinator commits it):"
if (( dry )); then echo "    (the host keys are made on a real run)"; else
    printf '    {"address": "127.0.0.1", "port": 22, "host_keys": ['
    sep=""; for p in "$S/host_keys"/*.pub; do printf '%s"%s"' "$sep" "$(cut -d' ' -f1,2 "$p")"; sep=", "; done; echo ']}'
fi
(( qubes )) && echo "Restart the AppVM to apply: the boot block restores the staged files and starts sshd."
cat <<'EOF'

Operator side, as `user` — printed, never run here; the key comes BEFORE this script:
    ssh-keygen -t ed25519 -f ~/.ssh/fabric_deck      # with a passphrase
    ssh-add ~/.ssh/fabric_deck
    fabric-ssh-hosts known-hosts > ~/.ssh/known_hosts.fabric   # once the pin is merged
    ssh -o UserKnownHostsFile=~/.ssh/known_hosts.fabric -o StrictHostKeyChecking=yes -i ~/.ssh/fabric_deck -t <login>@127.0.0.1 --watch
EOF
