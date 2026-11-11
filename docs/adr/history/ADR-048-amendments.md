# ADR-048 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-13 — loopback exempt from per-source penalties; MaxStartups above the deck's burst

§5 rule 1 gains two settings. On 2026-10-13 the fleet was restarted from
a session without an ssh-agent: every deck pane stopped at the key's
passphrase prompt, the abandoned connections counted as failed
authentications, and OpenSSH 10.0's PerSourcePenalties (authfail:5,
max:600) then dropped every new connection from 127.0.0.1 — the deck's
only address — so no account's session could start (sshd's journal:
"drop connection … penalty: failed authentication"). The deck also opens
about 75 connections at once, past the default MaxStartups 10:30:100.
The sshd listens on loopback only and takes keys only, so a penalty
there protects nothing. The owner's word, in the coordinator's session:
"yes, prepare the sshd exemption".

### Amendment 2026-10-31 — `attach`, the fifth word: the deck attaches to the account's harness pane

§5 rule 4 admits a fifth word, `attach`. FleetDeck part 2 (the owner's
approval of 2026-10-27 of rust-ui-dev-01's design) moves each account's
session out of the deck's ssh connection into the account's own headless
FleetDeck server, `agent-fabric-harness.service`, a user unit bootstrap
installs on every account; its one pane runs `enter --wait`. The deck no
longer starts a session over ssh: it attaches to that pane while the
account's tab is focused, and closing the connection leaves the session
running. `attach` is compared whole like the other four and reaches
`enter` as its mode `--attach`, so the root-owned `enter-ssh.conf` and
`enter` fence, the login shell and `record_client` are unchanged; the
refusal line names five words. `moveto --attach` is the same entry by
sudo. Built in agent-fabric #435; the read-back against the real binary
(the unit starts, attach draws, killing the ssh leaves claude, a stop
ends it with SIGTERM) waits for the owner's install of the binary
(install_fleetdeck.py) and goes to `docs/live-checks/`.

### Amendment 2026-11-04 — the harness pane's one `--resume`: after an idle account's `harness-restart`

§5 rule 4 says what the harness pane runs: `enter --wait`, which waits for
a person's Enter, at every start of `agent-fabric-harness.service` but one.
Restarting an account's harness to take a new fabric left its pane
waiting for an Enter until the owner went to it. The owner's word, 2026-11-04: a
restart that resumes the pane by itself, one account at a time, only an
idle one. `fabric-ctl <login|all> harness-restart` (python-dev-03's,
agent-fabric #478) checks the unit is active and every session in the
account's state record idle, has the account write a one-shot marker in
its own state directory (`harness_pane.py mark-resume`, as that login:
nothing writes into another login's home), restarts the unit, and reads
back a session that began after the restart; the unit's pane step that
finds the marker runs `--resume` and removes it. A marker older than ten
minutes, unreadable or not the account's own reads as none, and a restart
that fails after writing it removes it; when that removal fails too, the
marker lapses ten minutes after it was written, and a boot inside those
ten minutes resumes. The word set of `enter-ssh` is unchanged: `--resume`
was already one of its five. The read-back on three accounts is
docs/live-checks/2026-11-04-harness-restart.md.

### Amendment 2026-11-11 — A host reached over ssh listens beyond loopback; the coordinator's key on its operator

§7 left "more than one host: sshd beyond loopback" to the future. The
future arrived with `fabric-h2`, the second host (ADR-064 rule 1, A
2026-11-11), a VM on the Proxmox node s13337 that develop-qzapp
reaches over the LAN and its VPN.

One sshd there carries two things. The first is the coordinator's
hostexec to the operator account `op`, the registry's `ssh`, which
`fabric-host fabric-h2 check` read back live
(`docs/live-checks/2026-11-11-fabric-h2-registered.md`). The second,
later, is the deck's panes into each placed account. Rule 2 lets the
drop-in read only `/etc/ssh/authorized_keys/%u`. So once the drop-in
is applied there, the operator's own `~/.ssh/authorized_keys`, which
holds the coordinator's key today (put there by the owner with
`ssh-copy-id`), stops counting. The amendment puts that key in the
operator's file under `/etc/ssh/authorized_keys/`. It carries
`restrict` and a `from=` naming develop-qzapp's address as the host
sees it (10.10.10.3 in the live check). It has no forced command:
hostexec runs a command line, and a forced command would turn it into
`enter-ssh`'s five words. Rule 8 gains this key as its one exception.

The penalty exemption of 2026-10-13 is for loopback. Every client
there is local, and that does not carry over to a LAN address. The
deck's burst would come from one source, and whether it needs an
exemption is measured when an account is placed there, not assumed.

Until the drop-in is applied, `fabric-h2`'s entry pins the host keys
of AlmaLinux's own sshd. They were read on the host and match the
network scans. That sshd still accepts passwords, and no account is
placed there. The drop-in for a platform off Qubes (`ssh-operator.sh`
is the Qubes path) is still to be built, with the almalinux
provisioning profile (python-dev-02's j135).

Written by fabric-coordinator as job j706.
