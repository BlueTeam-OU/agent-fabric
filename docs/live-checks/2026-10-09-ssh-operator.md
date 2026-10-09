# 2026-10-09: does the operator reach each account over ssh, and only through enter-ssh?

**Why.** ADR-048 moves the deck's panes from `sudo` to ssh on 127.0.0.1, fenced
by root-owned keys files and a forced command. The read-back below is what the
record's acceptance waits on. A stub: every measured value is empty until the
owner has run the scripts and the coordinator has read back.

**Order, on develop-qzapp.**
1. As `user`: `ssh-keygen -t ed25519 -f ~/.ssh/fabric_deck` (with a passphrase); `ssh-add`.
2. In the TemplateVM, as root: `ssh-template.sh`; shut the template down.
3. In the AppVM, as root, before any restart, with moveto installed (`install.sh`): `ssh-operator.sh ~/.ssh/fabric_deck.pub`
   (sshd not yet installed: it stages, installs enter-ssh root-owned and the boot block, and leaves sshd alone).
4. The coordinator pins the printed host keys in `runtime/hosts/registry.json`
   `hosts.develop-qzapp.sshd` — BEFORE the restart.
5. Restart the AppVM. That restart is the test of the boot path.

**Measured on develop-qzapp, YYYY-MM-DD:**

| check | how | expected | measured |
|---|---|---|---|
| openssh-server came from the template, sshd disabled there | `rpm -q openssh-server`; in the template `systemctl is-enabled sshd` | installed; `disabled` | |
| phase one ran without sshd | step 3's output | staged, boot block written, "restart the AppVM to apply" | |
| after the restart sshd runs | `systemctl is-active sshd` | `active` | |
| it listens on loopback only | `ss -tlnp 'sport = :22'` | `127.0.0.1:22` and nothing else | |
| the host key equals the pin made before the restart | `fabric-ssh-hosts check develop-qzapp` | `match`, exit 0 | |
| a second restart keeps the host key | restart, `fabric-ssh-hosts check develop-qzapp` | `match`, exit 0 | |
| `sshd -t` on the restored configuration | `sudo sshd -t; echo $?` | 0 | |
| effective settings | `sudo sshd -T \| grep -Ei 'listenaddress\|passwordauth\|kbdinteractive\|permitrootlogin\|forwarding\|permittunnel\|gatewayports\|authorizedkeysfile\|allowusers'` | as the drop-in, AllowUsers the placed logins | |
| known_hosts from the registry | `fabric-ssh-hosts known-hosts > ~/.ssh/known_hosts.fabric`; connect with `StrictHostKeyChecking=yes` | no prompt, no warning | |
| each login reaches the forced command | `ssh … <login>@127.0.0.1 --watch` for every placed login | the status pane as that login | |
| `--wait`, `--resume`, `shell` | one login, each word | the dormant line; the session resumed after `~/.bashrc`; a shell | |
| any other command is refused | `ssh … <login>@127.0.0.1 id`, `'--wait; id'`, no command | `enter-ssh: refused…`, exit 2 | |
| `-L`, `-R`, `-D` refused | `ssh -N -L 9999:127.0.0.1:22 …`, `-R`, `-D 9998` | refused by sshd, no listener | |
| agent and X11 forwarding refused | `ssh -A -X … --watch`; `echo $SSH_AUTH_SOCK $DISPLAY` in the shell | both empty | |
| an agent cannot add a key | as a login: `ls -l /etc/ssh/authorized_keys/`; a key put in `~/.ssh/authorized_keys` | root-owned 0644; the key not accepted | |
| the forced command is root-owned, not a checkout's | `grep -h command= /etc/ssh/authorized_keys/* \| sort -u`; `ls -l /usr/local/libexec/agent-fabric/`; `cat …/enter-ssh.conf`; `ls -l /usr/local/share/moveto/enter` | one `command="/usr/local/libexec/agent-fabric/enter-ssh",restrict`; `enter-ssh` root:root 0755, conf root:root 0644 naming `/usr/local/share/moveto/enter`, itself root-owned; no path under /home | |
| an agent's checkout cannot change what the key runs | as a login, edit `~/projects/agent-fabric/runtime/provisioning/moveto/enter-ssh`; connect | the pane is unchanged (the installed copy ran) | |
| the restore puts a changed enter-ssh back | as root alter `/usr/local/libexec/agent-fabric/enter-ssh`; restart the AppVM; `cmp` with the staged copy | equal | |
| a login not placed is refused | `ssh … <unplaced>@127.0.0.1` | `Permission denied` | |
| the sudo path still works | `moveto <login> --watch` | the status pane, as before | |

**Not measured.**

**What it decides.**
