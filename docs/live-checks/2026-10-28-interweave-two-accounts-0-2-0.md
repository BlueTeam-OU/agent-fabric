# 2026-10-28 — rule 13 again, on InterWeave v0.2.0

Run by python-dev-02 and python-dev-03 (python-dev-02's job j97, from fabric-coordinator's j401), each as its own login, on one host, with `tests/live_interweave_two_accounts.py` of main b92f500d plus 22c800f4 (folded here), which adds `J92_PEER` to name the pair under test: since 0.2.0 rolled out the roster holds 30 rows, and main's script refused a roster of more than two. The question is the one of [the 0.1.0 run](2026-10-25-interweave-two-accounts.md) (agent-fabric ADR-064 §5 rule 13), asked again because the pin moved to v0.2.0 (#415), which changes the transport crates, before 0.2.0 is installed on the other 28 accounts.

What ran: the programs `interweave-install` put in place from the pinned v0.2.0 archive (`transportctl` and `transport-daemon` print `0.2.0+32ade966cff8`), run as the installed user units, daemon and carrier, with the 30-row roster's config. This differs from the 0.1.0 run, where the procedure's `serve` phase started plain processes: `serve` refuses a config the units wrote, so it and `stop` were skipped. Roster rows under test: python-dev-02 port 47101, python-dev-03 port 47102, both counting under `roster.valid_rows` on main's keys.

## What was measured

Run number `J92_RUN=1793184500000`.

| case | result |
|---|---|
| installed programs against the pin | both print the pin, on both accounts |
| roster | both rows count, on both accounts |
| python-dev-02 → python-dev-03, 241 bytes | receipted in 0.25 s; arrived, carrier `interweave`, verdict `ok` |
| python-dev-02 → python-dev-03, 205 018 bytes (chunked) | receipted in 0.24 s; arrived, `interweave`, `ok` |
| python-dev-03 → python-dev-02, 241 bytes | receipted in 0.22 s; arrived, `interweave`, `ok` |
| python-dev-03 → python-dev-02, 205 018 bytes | receipted in 0.25 s; arrived, `interweave`, `ok` |
| python-dev-02's second daemon on 47102, held by python-dev-03 | exit 1, `transport-daemon: the runtime: substrate: transport: Address already in use (os error 98)`; control on free 47191 started and ran |
| python-dev-03's second daemon on 47101, held by python-dev-02 | exit 1, the same line; control on free 47192 started and ran |

The controls are the procedure's, as set out on the 0.1.0 page: a receipt counts only as one queued copy whose delivery reached `done`, an arrival only as this run's computed ids with carrier `interweave` and verdict `ok`, a refusal only as exit 1 with `Address already in use` against a port shown held, and each refusal is paired with a start on a free port.

## What it decides

Rule 13's carrier half holds on v0.2.0 as it did on v0.1.0, under the installed units rather than plain processes: 0.2.0 may be installed on the remaining accounts. Nothing about rule 11's parity window follows from this page.

## Not verified

As python-dev-02 reported it:

- A unit's restart after a refused port (the units ran; none was refused at its own start).
- The duplicate window (InterWeave ADR-0055 decision 2).
- Load, an offline recipient.
- Mixed versions: both ends ran 0.2.0, so 0.1.0 ↔ 0.2.0, which the dual run carries until the other 28 accounts are installed, was not exercised.

The figures are from python-dev-02's REPLY 01a1821c-d6e7-7d07-9b84-65efc9cee023; result files are not committed. Two earlier attempts (1793175900000, 1793183932561) failed on coordination only: python-dev-03 was on another job, and its "starting" notice was refused as empty. The carrier did not fail.
