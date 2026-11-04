# 2026-10-24 — the carrier against real InterWeave daemons

Run by python-dev-02 (job j89), as that login, on one host, on the carrier of agent-fabric PR #365 before its review rounds ended (the head at the time is not recorded; the merged head is 2fb7e7f9). InterWeave was a checkout build of d2bbb46d, `transport-daemon` and `transportctl`, run from a scratch directory with its own XDG directories, so nothing of the account's own InterWeave, journal or state was touched. The question (agent-fabric ADR-064 §7, the build order before rule 13): does the carrier hold up across real daemons, not the fake one the suite uses.

The procedure is `tests/live_interweave_rehearsal.py`, not a suite member (it needs the InterWeave build). Two profiles, two daemons, two real minted PeerIds, a roster of the two signed with real OpenPGP keys made for the run. Carrier A is `bin/gzcoord-carrier run`; carrier B is the engine in the test process.

## What was measured

Run at 18:22 host time; every case passed (output kept in the job's scratch, not committed):

| case | result |
|---|---|
| roster of the two real PeerIds | both signatures verify; both rows count |
| A holds the lease and serves its adapter socket | yes, as an automated client on the `gzcoord` endpoint |
| A → B, a small message | journaled at B and receipted to A in 0.23 s |
| B → A | journaled at A (a real journal), in A's inbox spool and arrival log (carrier `interweave`, verdict `ok`), receipted in 0.28 s |
| a 204 953-byte message, past the ceiling and incompressible | chunked, reassembled, receipted in 0.24 s, byte for byte |
| a compressible 260 KB message | one compressed payload, byte for byte |
| B's daemon killed under a pending send | the send stays outstanding, not given up; on B's daemon back, delivered by A's retry under the same message, receipted after 4.4 s, journaled once |
| A's own daemon restarted | the carrier re-leased and the next message was delivered |
| a second client of the same endpoint | refused by the daemon (`EndpointInUse`) |
| SIGTERM | the carrier ends |

## What it decides

Nothing of the rule 11 switch: this is the carrier's behaviour against the transport, not a parity window.

## Not verified

- **The two-account run (rule 13).** `tests/live_interweave_two_accounts.py` is its procedure, run by two logins in phases (`init`, `roster`, `serve`, `exchange`, `portcheck`, `stop`). This page records no figures from it: its facts are the run's own, to be added by the coordinator who ran it, with the build and the commit it ran on.
- Real roster signatures: the rehearsal's roster is signed with throwaway keys; the suite tests the signing with real keys (`tests/test_gzcoord_carrier_roster.py`), and the real roster is the coordinator's.
- Two uids: the rehearsal is one account, so the socket and directory modes were not tested against a second user.
- A retry after the receiving carrier lost a copy is suppressed by the daemon's duplicate window until it expires (InterWeave ADR-0055 decision 2); not exercised here.
- Load, long runs, and the soak that rule 11 needs.
