---
role: "devex-tooling"
class: domain
topic: "uutils-date-3n-wrong"
description: "CI ubuntu-latest is Ubuntu 26.04 with uutils date; `date +%3N` is wrong in the first tenth of a second — time shell tests with EPOCHREALTIME"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - b1fc1ac64cb94b71
---

## CI ubuntu-latest is Ubuntu 26.04 with uutils date; `date +%3N` is wrong in the first tenth of a second — time shell tests with EPOCHREALTIME

GitHub's `ubuntu-latest` has been the ubuntu26 image (Ubuntu 26.04.1, bash 5.3.9, uutils coreutils
0.10.0 as `date`) since at least 2026-10-23. uutils `date +%3N` / `%6N` truncate the UNPADDED
nanosecond value: ns 034705108 prints `347` (should be `034`); 42 of 400 samples wrong, every
one with ns < 100000000. Plain `%N` and `%s.%N` are correct (always 9 digits).

Effect: InterWeave's tools/ci/test_with_display.sh repeated-signal case (t0=$(date +%s%3N))
read deaths at the 1s deadline as 235ms..1871ms; five red `tool self-tests` runs on 2026-10-24.
Fixed on PR #424 by timing with bash `EPOCHREALTIME`. Measured in ubuntu:26.04 podman: old
11/150 failing, fixed 0/150. ubuntu:24.04 (GNU date, bash 5.2) never reproduces it.

How to apply: a sub-second clock in a shell test or tool uses `${EPOCHREALTIME//[.,]/}`, never
`date %3N`. To reproduce a CI-only shell flake, run it in `docker.io/library/ubuntu:26.04`
(apt-get python3-minimal), not 24.04. Instrument both the code and the test's own measurement:
here the wrapper was right and the test's stopwatch lied. See [[solution-carried-2026-10-05]].

*References: ci-session-wrapper-measured-in-podman*

*Observed 2026-10-24 (devex-tooling)*
