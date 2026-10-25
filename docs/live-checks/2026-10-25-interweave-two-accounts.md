# 2026-10-25 — two accounts' carriers, and a port another account holds

Run by python-dev-02 and python-dev-03 (job j92), each as its own login, on one host, on the commit 8822aa6e of the branch `develop-qzapp/python-dev-02/feat/j92-adr-064-rule-13-max-priority` (main cece3f1f merged in). The question (agent-fabric ADR-064 §5 rule 13, the check before the dual run): with two instances under two accounts on the host, does one receive what the other sent (ADR-033 rule 4), and is one account's daemon refused the port another's holds. The second half is the carrier's side of the kernel claim InterWeave ADR-0055 decision 5 rests on; the InterWeave project's own measurement of it is p2p-network-dev-01's and is not repeated here.

What ran is what the fleet runs, not a checkout build: the programs installed in `~/.local/bin` by the pinned release (InterWeave v0.1.0, `runtime/interweave/release.json`), each checked first against the pin's `--version` and its SHA-256; each account's own `gzcoord` profile, key and PeerId; the two roster rows admitted in `runtime/interweave/roster.json` (python-dev-02 port 47101, python-dev-03 port 47102), both counting under `roster.valid_rows` on main's keys; and `bin/gzcoord-carrier run` from the checkout. The daemon and the carrier were plain processes started by the procedure, `tests/live_interweave_two_accounts.py` (not a suite member: it needs two logins), not systemd units, and ended by its `stop` phase, which also removed the `config.yaml` it had written. The messages were real INFO messages between the two logins, journaled and logged like any carried message.

## What was measured

The run's number `J92_RUN=1792956462870` makes the MESSAGE-IDs; every figure below is from the second run (the first is in the last section).

| case | result |
|---|---|
| installed programs against the pin | both print the pinned `--version`, both digests equal `program_sha256` |
| roster | both rows count |
| python-dev-02 → python-dev-03, a 241-byte message | queued as carried; receipted to the sender in 0.29 s; python-dev-03's arrival log holds its id with carrier `interweave`, verdict `ok` |
| python-dev-02 → python-dev-03, 205 018 bytes (past the 48 KiB ceiling, incompressible, so chunked) | receipted in 0.38 s; arrived, carrier `interweave`, verdict `ok` |
| python-dev-03 → python-dev-02, 241 bytes | receipted in 0.36 s; arrived here, carrier `interweave`, verdict `ok` |
| python-dev-03 → python-dev-02, 205 018 bytes | receipted in 0.36 s; arrived here, carrier `interweave`, verdict `ok` |
| a second daemon of python-dev-02 (throwaway profile of its own) told to listen on 127.0.0.1:47102, which python-dev-03's daemon holds | exits 1 at once: `transport-daemon: the runtime: substrate: transport: Address already in use (os error 98)` |
| the same, python-dev-03's second daemon on 47101, held by python-dev-02's | exits 1 with the same line |

The controls:

- **Receiving.** Each account waits for the *two message ids the other computes from the run number*, not for "any arrival", so an older message in the log cannot satisfy it; the receipt is the sender's, taken from the carrier's outstanding list, so a receipt without the arrival (or an arrival without the receipt) fails the phase. The arrival is read from the receiving account's own `gzcoord-arrivals.jsonl`, written by its own carrier. In the second run python-dev-02's inbox rendered python-dev-03's two messages without a validity warning (python-dev-03's side was not looked at for this).
- **Refusing.** Before the second daemon starts, the phase connects to the other account's port and requires an answer: the port is held *now*, so the refusal cannot be a port nobody has. After it, the same procedure starts the same program with the same kind of configuration on a free port (47191 for python-dev-02, 47192 for python-dev-03, each its own roster port + 90), and that daemon must start and keep running for 15 s: python-dev-02's did, as did python-dev-03's. A refusal and a start therefore differ only by the port.
- **A control that can fail.** In the first run both accounts ran the phase in the same minute with one free port, 47190; each control daemon found it taken by the other and exited with the same `Address already in use` line, and the phase reported `UNEXPECTED` on python-dev-03's side. That is the control failing when it should, and the defect was in the procedure (below).

## What it decides

For ADR-064 rule 13: the carrier half is met on one host and two uids: two carriers from the pinned programs, each receiving what the other sent, small and chunked, with the sender's receipt and the receiver's arrival record agreeing; and the kernel refused a second daemon the port another account's daemon holds, as `EADDRINUSE`, at the daemon's start, with exit 1. The daemon unit's `Restart=on-failure` with `RestartPreventExitStatus=2` rests on exactly that exit status; the procedure did not run it under systemd, so the unit's retry is still unmeasured here. Nothing about rule 11's parity window follows from this page.

## Not verified

- Units. The daemon and the carrier were run as processes; the user units (`interweave-daemon@gzcoord`, the client unit), their restart on a refused port and lingering across a session's end were not exercised.
- The duplicate window (InterWeave ADR-0055 decision 2): a rerun with the same run number was not attempted; the second run's new number is what kept the first run's ids out of its way.
- Load, a long run, an offline recipient, `TO-ROLE` and broadcast; the rollback drill. Those are the soak's (rule 11).
- One run of each measurement. The refusals and the receipts repeated across the two accounts and the two directions, but not across restarts.
- A refusal by a *client* of the same endpoint, and the daemon's port while the holder is mid-restart.

## What the run found in the procedure

Three defects of `tests/live_interweave_two_accounts.py`, none of the carrier, fixed on the branch before the second run: the share directory was created 1755 (the umask cut `makedirs`' mode), so the second account could not write its result; the one control port made two simultaneous port checks collide; and the test messages carried no `PROJECT` and the role `r`, which the receiver's inbox rendered as INVALID although the carrier journaled and logged them as `ok`. The first run's receipts and arrivals (0.33 and 0.63 s one way, the same ids' arrival the other) are not counted here for that last reason.
