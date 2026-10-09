#!/usr/bin/env bash
# Apply what ssh-operator.sh staged under /rw/config/agent-fabric-ssh/ to
# /etc/ssh, check it, and only then start sshd (agent-fabric ADR-048 §5
# rules 1-2, 6). ssh-operator.sh copies this file into the staging
# directory as restore.sh, root-owned, and the /rw/config/rc.local block
# runs that copy at every boot: root never runs a file from a checkout a
# login can write. ssh-operator.sh also runs it once, sshd there or not.
#
# Every boot of a Qubes AppVM brings /etc back from the template, so
# everything is written each time, never "only if missing". sshd is not
# started unless `sshd -t` passes on the restored configuration: a broken
# drop-in leaves sshd down, never up with the distribution's defaults.
set -euo pipefail
S="${AGENT_FABRIC_SSH_STAGE:-/rw/config/agent-fabric-ssh}"
ETC="${AGENT_FABRIC_SSH_ETC:-/etc/ssh}"
LIBEXEC="${AGENT_FABRIC_SSH_LIBEXEC:-/usr/local/libexec/agent-fabric}"
say() { echo "agent-fabric-ssh: $*" >&2; }
# The forced command and its conf: /usr/local persists on Qubes, but a copy
# gone or changed there (by hand, or a /rw/usrlocal restore) is put back from
# the staged one, root-owned, so every key's command= runs what was staged.
install -d -m 0755 -o root -g root "$LIBEXEC"
for f in enter-ssh:0755 enter-ssh.conf:0644; do
    [[ -f "$S/${f%:*}" ]] || continue
    cmp -s "$S/${f%:*}" "$LIBEXEC/${f%:*}" || install -m "${f#*:}" -o root -g root "$S/${f%:*}" "$LIBEXEC/${f%:*}"
    chown root:root "$LIBEXEC/${f%:*}"; chmod "${f#*:}" "$LIBEXEC/${f%:*}"
done
sshd=$(command -v sshd || echo /usr/sbin/sshd)
if [[ ! -x "$sshd" ]]; then
    say "sshd is not installed (ssh-template.sh in the TemplateVM); enter-ssh installed, sshd left alone"
    exit 0
fi
[[ -f "$S/50-agent-fabric.conf" ]] || { say "nothing staged in $S; run ssh-operator.sh"; exit 1; }

install -d -m 0755 -o root -g root "$ETC/sshd_config.d" "$ETC/authorized_keys"
install -m 0600 -o root -g root "$S/50-agent-fabric.conf" "$ETC/sshd_config.d/50-agent-fabric.conf"

# The keys directory is exactly the staged one: a login no longer placed
# loses its file here too, not only in the staging copy.
for f in "$ETC/authorized_keys"/*; do
    [[ -e "$f" ]] || continue
    [[ -f "$S/authorized_keys/${f##*/}" ]] || rm -f -- "$f"
done
for f in "$S/authorized_keys"/*; do
    [[ -f "$f" ]] && install -m 0644 -o root -g root "$f" "$ETC/authorized_keys/${f##*/}"
done

# The AppVM's own host keys, made once by ssh-operator.sh: restoring them
# keeps the registry's pin valid across reboots. Fedora once kept private
# host keys group ssh_keys; where that group exists it is used, 0600 either way.
grp=root
getent group ssh_keys >/dev/null 2>&1 && grp=ssh_keys
for k in "$S/host_keys"/ssh_host_*_key; do
    [[ -f "$k" ]] || continue
    install -m 0600 -o root -g "$grp" "$k" "$ETC/${k##*/}"
    install -m 0644 -o root -g root "$k.pub" "$ETC/${k##*/}.pub"
done

if ! "$sshd" -t; then
    say "sshd -t refused the restored configuration; sshd not started"
    exit 1
fi
systemctl enable sshd.service
# restart, not start: a running sshd would keep the configuration it read
systemctl restart sshd.service
say "sshd configured from $S and started"
