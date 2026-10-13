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
