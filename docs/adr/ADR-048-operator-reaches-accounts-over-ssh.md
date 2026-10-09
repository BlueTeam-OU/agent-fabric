# ADR-048 — The operator reaches agent accounts over ssh

**Date:** 2026-10-09
**Status:** Proposed
**Decision Makers:** the owner (ssh for the deck's panes, the forced command, the Qubes split); drafted by fabric-coordinator
**Scope:** `runtime/provisioning/moveto/enter-ssh`, `runtime/provisioning/platform/qubes/ssh-template.sh`, `runtime/provisioning/platform/qubes/ssh-operator.sh`, `runtime/provisioning/platform/qubes/ssh-restore.sh`, `tools/fabric/ssh_hosts.py`, `bin/fabric-ssh-hosts`, the `sshd` property of a host in `runtime/hosts/registry.json`; how the operator's panes enter an account
**Pillar:** P3
**Evidence:** docs/live-checks/2026-10-09-ssh-operator.md

## 1. Context and Problem

The operator, the owner at the `user` login's Fleet Deck, enters an
agent account for three kinds of pane: a shell, the harness (`--wait`,
`--resume`) and the status pane (`--watch`). Today every one of them is
`moveto`, which is `sudo -n -u <login>` from `user`. That makes the deck's
every pane depend on `user`'s unrestricted sudo, gives the entered process
sudo's reset environment rather than the account's login, and starts
`--resume` before the account's `~/.bashrc` has run — so a session resumed
from a pane can miss what the account's shell sets.

Every account of the fleet lives on one host today, a Qubes AppVM
(`develop-qzapp`, Fedora), where only `/rw` (`/home`, `/rw/config`,
`/usr/local`) persists and `/etc` and `/usr` come back from the
TemplateVM at every boot. openssh-server is not installed there.

## 2. Decision

The operator reaches each agent account over ssh to the loopback address,
with one operator key whose every use is fenced by a forced command,
`enter-ssh`, that does one of four things and nothing else. sshd takes
keys only from a root-owned directory, so no agent can add a key to its
own account. The host key is pinned in the host registry from a read on
the host, and `known_hosts` is generated from the registry. sudo stays as
the break-glass path. On Qubes the package comes from the TemplateVM and
everything else is saved under `/rw/config` and restored at boot.

## 3. Alternatives Considered

- **Keep sudo for the panes.** Rejected: every pane rides the operator's
  full sudo, the entered shell is not the account's login, and `--resume`
  runs before `~/.bashrc`.
- **A restricted sudoers rule per account** (`user ALL=(<login>) NOPASSWD:
  /usr/local/share/moveto/enter`). Rejected: sudo still resets the
  environment and skips the login shell, and sudoers lives in `/etc`,
  which needs the same `/rw` restore as sshd without sshd's per-key fence.
- **`~/.ssh/authorized_keys` in each account.** Rejected: the account owns
  that file, so an agent could add a key of its own to itself, or drop
  the `restrict` from the operator's.
- **`ssh-keyscan` to fill `known_hosts`.** Rejected: it trusts whatever
  answers on the first contact, which is what pinning exists to refuse.
- **Installing openssh-server from the AppVM.** Rejected: `/usr` is reset
  at boot; a package installed there is gone on the next one.
- **Reusing the registry's `ssh` property** for the host's sshd. Rejected:
  `ssh` is already the coordinator's destination for a host's operator
  account, and `null` there means "the host this registry is read on"
  (fleet, new-agent and lint read it so); giving the local host an object
  would turn it into a remote one. The host's sshd is its own property,
  `sshd`.

## 4. Rationale

A forced command in a root-owned `authorized_keys` file is the fence ssh
gives per key: whatever the client asks, sshd runs that command, with the
request in `SSH_ORIGINAL_COMMAND`, and `restrict` turns off every
forwarding and the agent, X11 and user-rc for that key even if the server
configuration were loosened. Accepting four exact words, compared whole,
leaves no parsing to get wrong. The argument reaches `enter` as a
positional parameter of a login shell, so it is never shell text, and the
login shell makes `--resume` run after the account's own start-up files.

The forced command, and the `enter` it runs, are root-owned installed
copies, never an account's checkout. A checkout is the agent's to write:
an `enter-ssh` or `enter` there could be rewritten to show the operator a
spoofed terminal or to capture what the operator types into the pane.
So `enter-ssh` is installed `root:root 0755` in
`/usr/local/libexec/agent-fabric/`, and it runs the `enter` named by the
one line of the root-owned `enter-ssh.conf` beside it — moveto's
installed `/usr/local/share/moveto/enter` (`install.sh`). A file, not an
environment variable, names it: nothing a client sends reaches it, and a
test installs its own copy beside its own conf. Without moveto installed
the provisioning refuses; it never falls back to a checkout's `enter`.

Loopback-only listening keeps the single-host deployment unreachable from
the network: the fence is the address, then `AllowUsers`, then the key,
then the forced command.

## 5. Binding Rules

1. sshd on a single-host deployment listens on `127.0.0.1` only. It takes
   public keys only: no password, no keyboard-interactive, no root login.
   No forwarding of any kind (TCP, stream-local, agent, X11), no tunnel,
   no gateway ports. `AllowUsers` names exactly the logins the registry
   places on that host. The settings live in one drop-in,
   `/etc/ssh/sshd_config.d/50-agent-fabric.conf`, and `sshd -t` passes
   before sshd is enabled or restarted.
2. `AuthorizedKeysFile` is `/etc/ssh/authorized_keys/%u`: a directory
   `root:root 0755`, one file per placed login, `root:root 0644`. No
   account's own `~/.ssh/authorized_keys` is read.
3. Each file holds the one operator key, with
   `command="/usr/local/libexec/agent-fabric/enter-ssh",restrict,pty`. That
   `enter-ssh` and its `enter-ssh.conf` are `root:root` (0755, 0644); the
   conf names moveto's installed `enter`, and no path in a forced command
   or a conf is in an account's home.
   The operator key is made by the owner as `user`
   (`ssh-keygen -t ed25519 -f ~/.ssh/fabric_deck`), with a passphrase,
   loaded into ssh-agent; the provisioning script takes its public half
   as an argument and never generates a key.
4. `enter-ssh` accepts exactly one of `--wait`, `--watch`, `shell`,
   `--resume` in `SSH_ORIGINAL_COMMAND`, compared whole: nothing else, no
   second word, no metacharacter, no newline. It runs `enter` in a login
   shell of the account (`bash -lc`) with the word passed as a positional
   parameter, never placed in the command string. Anything else is one
   line on stderr and exit 2.
5. A host's sshd is `sshd` in its registry entry: `null` (or absent) until
   provisioned, then `{"address", "port", "host_keys"}`, `host_keys` the
   host's public keys as `<type> <base64>`. The keys are read on the host
   from `/etc/ssh/ssh_host_*_key.pub` (the provisioning script prints
   them) and pinned by fabric-coordinator; `fabric-ssh-hosts check <host>`
   compares the pin with the host and fails on any difference.
   `known_hosts` is generated from the registry
   (`fabric-ssh-hosts known-hosts`), never from `ssh-keyscan`. The shape
   is held by the hosts schema.
6. On Qubes the split is by what persists, and provisioning is two
   phases, because openssh-server reaches the AppVM only with the restart
   that follows the template's change, and that restart is the test.
   The TemplateVM gets the package only (`ssh-template.sh`: `dnf install
   -y openssh-server`, then sshd explicitly disabled, since the
   distribution's preset may enable it), never our configuration and
   never a running sshd, so no other AppVM on that template changes.
   Phase one, `ssh-operator.sh` in the AppVM, runs no package manager and
   needs no sshd: it stages under `/rw/config/agent-fabric-ssh/`
   (root-only) the drop-in, one keys file per placed login, the AppVM's
   host keys, `enter-ssh` with its conf, and a root-owned copy of
   `ssh-restore.sh`, installs one marked, idempotent block in
   `/rw/config/rc.local`, and runs the restore once: it installs
   `enter-ssh` into `/usr/local/libexec/agent-fabric/` (`/usr/local`
   persists on Qubes, through `/rw/usrlocal`) and goes on to sshd only
   when sshd is already there. At every boot the restore reinstalls
   `enter-ssh` and its conf when either is absent or differs from the
   staged copy. The host keys are made once with
   `ssh-keygen` and never regenerated by a re-run: ed25519, ecdsa and
   rsa, all three, because Fedora's sshd-keygen fills any missing type
   at every start of sshd, and `/etc` is fresh at every boot, so a type
   not staged would be a new, unpinned key each time. Phase two, at
   every boot, restores the staged files into `/etc/ssh` with their
   owners and modes (private host keys 0600 root, group `ssh_keys` where
   it exists), runs `sshd -t`, and only then enables and starts sshd;
   with sshd absent it logs one line and does nothing. The key is pinned
   from phase one's output before the restart, and the restart proves it.
   Off Qubes `/etc` persists: phase two runs once, at provisioning.
7. sudo (`moveto`) stays the break-glass path: nothing here removes it,
   and a pane that cannot reach sshd is entered through it.
8. Agents' own ssh keys stay future (ADR-038): no agent login holds an
   ssh key that reaches another account, and no key but the operator's
   is placed under `/etc/ssh/authorized_keys/`.

## 6. Consequences

- The deck's panes run as the account's login, after its own start-up
  files, without the operator's sudo.
- One more daemon on the host, loopback only; its configuration is
  reapplied at boot on Qubes and checked with `sshd -t`.
- The operator key's passphrase and the host-key pin are the owner's and
  the coordinator's hands; nothing pins a key on its own.
- A new placed login needs the script re-run (its `AllowUsers` and its
  keys file).

## 7. Future Evolution

- `moveto --via ssh|sudo` (ssh by default once provisioned) and the deck
  recognising an ssh pane, with `docs/fleet-deck/tab-states.md` amended.
- moveto's `install.sh` installing `enter-ssh` and its conf beside
  `enter`, under its manifest, so `fabric-status` reports a stale copy;
  until then ssh-operator.sh and its restore install them.
- More than one host: sshd beyond loopback, and per-host addresses in the
  registry; agents' own keys (ADR-038).

## 8. Decision Status

Proposed: the owner approved the approach in the coordinator's plan; this
record awaits the owner's acceptance in its pull request, and the live
check's read-back.

## References

- ADR-010 (hosts, placement, hostexec), ADR-029 (the control plane),
  ADR-038 (an agent's own keys), ADR-044 (the deck's operator).
- `runtime/provisioning/moveto/enter`, `runtime/provisioning/platform/qubes/agent-fabric-accounts.rc`.
- `docs/live-checks/2026-10-09-ssh-operator.md`.
