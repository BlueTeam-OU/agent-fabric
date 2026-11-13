# 2026-11-13: control's second carrier, read back between two accounts

**Why.** ADR-029 rule 18 keeps InterWeave off for an account until
`runtime/control/config.json` `control_carrier` names it `dual`, and the
build (#571, python-dev-02's j141, 8 work and 3 fix commits) named its
two-account live read-back as not yet run. This is that read-back. It
decides whether the fleet is switched to `dual` (job j793).

**What ran.** `tests/live_control_dual.py` at origin/main `74a6f810`, in
two sessions on develop-qzapp: `user` (fabric-coordinator) as the
operator, `python-dev-01` as the peer (its job j234, REQUEST
01a1d37a). It runs the installed InterWeave programs, each account's own
`gzcoord` profile and PeerId and the committed roster, but neither the
fleet's relay nor its `fabric:control` channel. Each account's agentd
here was a scratch process with `FABRIC_CONTROL_CARRIER=dual`, against
a private relay that the operator's `ask` killed in the second run. The
accounts' own agentd units kept running as they were.

**Measured, 2026-11-13 05:57–06:02Z.**

| phase | account | result |
|---|---|---|
| check | both | transportctl, transport-daemon `0.2.0+32ade966cff8`, the pinned programs by digest; interweave-human prints the same version (its digest is not in `release.json`: not checked); the roster counts 30 rows, both accounts among them |
| render | both | `interweave-start` as the account: re-rendered, both units active; the profile lists `fabric-control` (enabled) beside `gzcoord` (enabled, default, leased by automated-client) |
| serve | both | scratch agentd up, "also on InterWeave (fabric-control); the relay stays the record" |
| ask 1: both carriers up | operator | `fabric-ctl` ping of python-dev-01, exit 0, `status: ok`. Arrivals: the reply by InterWeave at the operator's agentd and at `fabric-ctl`, verdict `ok`; the same reply id by the relay at `fabric-ctl`, verdict `unauthenticated`. The row is the InterWeave copy |
| ask 2: relay dead after accepting the request | operator | exit 0, `status: ok`, latency 158 ms; `fabric-ctl` says the relay read failed (connection refused); the reply arrived by InterWeave alone, verdict `ok` |
| stop | both | scratch processes ended; no process of the script left (python-dev-01 checked with `kill -0`) |

The script's own verdicts: run 1 PASS (one InterWeave copy counted, the
relay's the same), run 2 PASS (the answer came with the relay stopped
mid-run).

**Then, the fleet's profiles.** `fabric-ctl all interweave-start`,
right after the check: 27 accounts re-rendered and 3 already rendered (`user`,
`python-dev-01` by this check, `python-dev-02` by its build), every
account `daemon active, client active`; `fabric-ctl all interweave`
after it read 30 accounts `ok`, pinned, both units, channel `ok`. Every
account's profile now carries `fabric-control`, which a `dual` agentd
needs.

**The InterWeave part bound.** #571 measured it on this path before the
dual run: a 60000-byte record passes and a 66000-byte one does not, so
parts are split at 32 KiB, rule 18's ceiling.

**What it decides.**
- Rule 18 is built and read back on one host between two accounts:
  `control_carrier` is switched to `dual` for the fleet in the same
  pull request, and reaches each account with its next fabric upgrade.
- The relay stays the transport of record (ADR-029 §2): `dual` adds a
  carrier, it removes none.

**Not measured.**
- A second host: fabric-h2 has no fleet account yet, and it cannot dial
  back to develop-qzapp (2026-11-11 record). A control request is
  answered over the connection the operator opened, which this check
  does not exercise across hosts.
- interweave-human's digest and the state records, the operator's own
  account and a re-split of an oversized part: #571's named limits.
- The fleet's own agentd units on `dual`: they take it at the upgrade
  that follows the merge, and `fabric-ctl all ping` afterwards is that
  read-back.
