---
role: "devex-tooling"
class: domain
topic: "fast-clock-through-bash-env"
description: "Speed up a bash suite whose script under test naps on a wall-clock SECONDS deadline — source a sleep() through BASH_ENV that ages SECONDS, keep real latency on `command sleep`, and prove the clock is live with a control case."
tier: 2
knowledge_scope: full
distilled_at: "2026-09-28"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 3f5e05d034e83a2d
---

## Speed up a bash suite whose script under test naps on a wall-clock SECONDS deadline — source a sleep() through BASH_ENV that ages SECONDS, keep real latency on `command sleep`, and prove the clock is live with a control case.

A bash script that keeps a deadline in `SECONDS` and naps with `sleep`
can be tested at full fidelity in a fraction of the wall time without
touching it: run it with `BASH_ENV=<file>` where the file defines
`sleep() { SECONDS=$(( SECONDS + n )); }` — assigning SECONDS makes it
count on from the value, so the deadline arrives after exactly the
polls it would have (a no-op sleep would spin instead). Anything that
must cost real time — a mock's latency standing for API time — uses
`command sleep`, since the mock inherits BASH_ENV too. Keep every
timeout as written (shortening them erodes thresholds like
MAX_CONSECUTIVE_FAILURES), keep one or two real-clock cases that prove
the real loop terminates, and add a CONTROL case: a 6s expiry must
report 6s while the suite's clock barely moves — if BASH_ENV stops
reaching the script the suite goes slow AND red, never silently slow.
Bonus: overshoot becomes a number, so `--interval 60 --timeout 6`
reporting "after 60s" catches an unclamped nap that a real-clock
`waited >= 2` never could.

**Why:** gzapp `tools/gh/test_wait-merged.sh` went 223s → 67s (214s →
~53s in CI) on 2026-09-18 (#886, a654a5c7) after two earlier attempts
to shorten the timeouts had been reverted for good reasons.
**How to apply:** any `tools/gh` or `tools/checks` suite that waits on
a script's real deadline; measure baseline from a scratch copy first
(editing a running bash script shifts offsets under it).

*Observed 2026-09-18 (devex-tooling)*
