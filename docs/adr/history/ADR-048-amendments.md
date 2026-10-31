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
