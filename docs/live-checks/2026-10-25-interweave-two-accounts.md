# 2026-10-25 — two accounts' carriers, and a port another account holds

Run by python-dev-02 and python-dev-03 (job j92), each as its own login, on one host, with `tests/live_interweave_two_accounts.py` of the branch `develop-qzapp/python-dev-02/feat/j92-adr-064-rule-13-max-priority` (PR #382): python-dev-03 on 35e0778c, python-dev-02 on ef991d29, whose one difference is that the receive phase no longer treats the other account's already-arrived ids as a reused run number (it refused python-dev-02's own exchange once, because python-dev-03 had sent first). Main cece3f1f is merged in. The question (agent-fabric ADR-064 §5 rule 13, the check before the dual run): with two instances under two accounts on the host, does one receive what the other sent (ADR-033 rule 4), and is one account's daemon refused the port another's holds. The second half is the carrier's side of the kernel claim InterWeave ADR-0055 decision 5 rests on; the InterWeave project's own measurement of it is p2p-network-dev-01's and is not repeated here.

What ran is what the fleet runs, not a checkout build: the programs installed in `~/.local/bin` by the pinned release (InterWeave v0.1.0, `runtime/interweave/release.json`), each checked first against the pin's SHA-256 and `--version` (and checked again by every phase that starts one); each account's own `gzcoord` profile, key and PeerId; the two roster rows admitted in `runtime/interweave/roster.json` (python-dev-02 port 47101, python-dev-03 port 47102), both counting under `roster.valid_rows` on main's keys; and `bin/gzcoord-carrier run` from the checkout. The daemon and the carrier were plain processes started by the procedure, not systemd units, and ended by its `stop` phase, which also removed the `config.yaml` it had written. The messages were real INFO messages between the two logins, journaled and logged like any carried message.

## What was measured

The run's number `J92_RUN=1792957374628` makes the MESSAGE-IDs. The figures are from the third run of the procedure; the two before it are in the last section.

| case | result |
|---|---|
| installed programs against the pin | both print the pinned `--version` and their digests equal `program_sha256`, on both accounts |
| roster | both rows count |
| python-dev-02 → python-dev-03, 241 bytes | queued by the carrier (`carried` 1, `queued` 1); the delivery reached state `done` (the recipient's receipt) in 0.33 s; python-dev-03's arrival log holds its id with carrier `interweave`, verdict `ok` |
| python-dev-02 → python-dev-03, 205 018 bytes (past the 48 KiB ceiling; zlib takes it to about 118 KB, still past it, so chunked) | receipted in 0.35 s; arrived, carrier `interweave`, verdict `ok` |
| python-dev-03 → python-dev-02, 241 bytes | receipted in 0.24 s; arrived here, carrier `interweave`, verdict `ok` |
| python-dev-03 → python-dev-02, 205 018 bytes | receipted in 0.29 s; arrived here, carrier `interweave`, verdict `ok` |
| a second daemon of python-dev-02 (throwaway profile of its own) told to listen on 127.0.0.1:47102, which python-dev-03's daemon holds | exits 1 at once: `transport-daemon: the runtime: substrate: transport: Address already in use (os error 98)` |
| the same, python-dev-03's second daemon on 47101, held by python-dev-02's | exits 1 with the same line |

The controls:

- **Receiving.** Each account waits for the *two message ids the other computes from the run number*, and counts only an arrival whose carrier is `interweave` and verdict `ok`, read from its own `gzcoord-arrivals.jsonl`. Its own sends count as receipted only when the carrier answered that it carried and queued exactly one copy and the delivery record of that id reached state `done` (an abandoned delivery is another state). The phase refuses a run number whose own ids are already in the account's outbox, which the third run's tooling showed by refusing the second run's number (`J92_RUN 1792956462870 was used before …`, exit 2) against the carrier that had delivered it. A send that reached nobody, or a delivery settled in an earlier run, therefore cannot stand for this run's receipt.
- **Refusing.** Before the second daemon starts, the phase connects to the other account's port and requires an answer: the port is held now, so the refusal cannot be a port nobody has. The refusal counts only as exit 1 with `Address already in use` in the daemon's output; any other early exit fails the phase. After it, the same procedure starts the same program with the same kind of configuration on a free port (47191 for python-dev-02, 47192 for python-dev-03, each its own roster port + 90), and that daemon must start and keep running for 15 s: both did. A refusal and a start therefore differ only by the port.
- **A control that can fail.** In the first run both accounts ran the phase in the same minute with one free port, 47190; each control daemon found it taken by the other and exited with the same `Address already in use` line, and the phase reported `UNEXPECTED` on python-dev-03's side. That is the control failing when it should, and the defect was in the procedure (below).

## What it decides

For ADR-064 rule 13: the carrier half is met on one host and two uids: two carriers from the pinned programs, each receiving what the other sent, small and chunked, with the sender's receipt and the receiver's arrival record agreeing; and the kernel refused a second daemon the port another account's daemon holds, as `EADDRINUSE`, at the daemon's start, with exit 1. The daemon unit template in the v0.1.0 archive (`interweave-daemon@.service`, installed to `~/.config/systemd/user/`) sets `Restart=on-failure` and `RestartPreventExitStatus=2`, so a start refused with exit 1 is retried by the unit; that was read in the file and not run, since no unit was started. Nothing about rule 11's parity window follows from this page.

## Not verified

- Units. The daemon and the carrier were run as processes; the user units, their restart on a refused port and lingering across a session's end were not exercised.
- The duplicate window (InterWeave ADR-0055 decision 2): a rerun with the same run number is refused by the procedure before any send, so the window was not exercised.
- Load, a long run, an offline recipient, `TO-ROLE` and broadcast; the rollback drill. Those are the soak's (rule 11).
- One passing run of each measurement on the final script, python-dev-03's on 35e0778c and python-dev-02's on ef991d29. The earlier runs below agree with them but ran a script since changed.
- A refusal by a *client* of the same endpoint, and the daemon's port while the holder is mid-restart.
- The result files and outputs are not committed; the figures above are from the two accounts' phase output, which each account sent to the other as a message.

## What the runs found in the procedure

None of it was the carrier. The first run (8822aa6e's predecessor, exchange and port check in the same minute) failed on three defects of `tests/live_interweave_two_accounts.py`, fixed before the second run: the share directory was created 1755 (the umask cut `makedirs`' mode), so the second account could not write its result; the one control port made two simultaneous port checks collide; and the test messages carried no `PROJECT` and the role `r`, which the receiver's inbox rendered as INVALID although the carrier journaled and logged them as `ok`. The second run (8822aa6e, run number 1792956462870) passed in both directions with receipts of 0.29 to 0.38 s and the same two refusals. The blind review of PR #382 then found, in the script, that a send answer was never checked and a reused run number could pass on an earlier run's records, that the port check did not verify the programs against the pin, that the check ran a program before its digest, that `stop` could remove a config it had not written, and that any early exit counted as a refusal; all were fixed (35e0778c) and the third run above is of that script.
