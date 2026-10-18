---
role: "p2p-network-dev"
class: domain
topic: "domain-strace-inject-a-platform-denial"
description: "To reproduce on a dev host a syscall failure only a device or a CI kernel produces (SELinux EACCES on link, EADDRINUSE on a reuse-port connect), run the test under strace's fault injection and compare main against the fix"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - fd66714b3c72d413
---

## To reproduce on a dev host a syscall failure only a device or a CI kernel produces (SELinux EACCES on link, EADDRINUSE on a reuse-port connect), run the test under strace's fault injection and compare main against the fix

Used twice in InterWeave, 2026-10-14:
- #276: `strace -f -e inject=link,linkat:error=EACCES <test binary>` reproduced the Pixel's SELinux denial on
  the host — origin/main failed 28 of 31 custody tests with the device's exact error
  (`Storage(Io(Os { code: 13 }))`), the fix head passed 31.
- #277: the CI runner's EADDRINUSE on a `PortUse::Reuse` dial could not be reproduced by any socket arrangement
  on the host kernel; injecting the errno on the dial's `connect`/`bind` exercised the fallback path. The
  amendment recorded the kernel trigger as observed on the runner and not reproduced, the strace run as
  evidence in the PR body, never claimed as CI.

Limits: it proves the code's handling of the errno, not that the platform returns that errno (the device or
runner run does that), and not that the replacement syscall is allowed there (#276's renameat2 needed the
device re-run to show the policy and seccomp allow it).

**How to apply:** when a failure comes from a platform you do not have, inject its errno at the syscall
under strace, run main (must fail the same way — the positive control) and the fix (must pass); keep a unit
seam with an injected errno as the CI-runnable test.

*Observed 2026-10-15 (p2p-network-dev)*
