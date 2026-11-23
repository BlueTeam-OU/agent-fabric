---
role: "devex-tooling"
class: domain
topic: "uutils-timeout-kill-after-child-only"
description: "CI's ubuntu-26.04 timeout is uutils 0.10.0 — --kill-after KILL hits the child only; use gnutimeout (shipped) for a bound that reaches descendants"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 5a123f98972d796c
---

## CI's ubuntu-26.04 timeout is uutils 0.10.0 — --kill-after KILL hits the child only; use gnutimeout (shipped) for a bound that reaches descendants

ubuntu-26.04's `/usr/bin/timeout` is uutils coreutils 0.10.0. Its first
signal (TERM) reaches the whole process group, but the `--kill-after`
KILL reaches only the direct child, so a descendant ignoring TERM
outlives the bound and holds a `$(...)` or step output open. Measured
in ubuntu:26.04 on 2026-11-04: a 1 s limit over a TERM-deaf child took
30 s with `timeout` and 3 s with `gnutimeout` (GNU 9.7, package
gnu-coreutils, shipped in the image).

InterWeave #534 hit it: `tools/ci/test_pip_install.sh`'s deaf case ran
60 s in CI (run 41877271528) though it passed on the GNU host. The fix,
d3f50ac39: `pip_install.sh` takes `gnutimeout` if on PATH, else a
`timeout` whose `--version` says GNU coreutils, else exit 2.

**How to apply:** any CI script that relies on timeout's group kill or
--kill-after: choose gnutimeout first, and run its self-test in
`podman run ubuntu:26.04` before pushing (see [[uutils-date-3n-wrong]],
same image, same class of trap).

*References: uutils-date-3n-wrong*

*Observed 2026-11-04 (devex-tooling)*
