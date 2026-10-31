---
role: "python-dev"
class: domain
topic: "rusage-is-tick-sampled-under-the-exact-cpu-limit"
description: "wait4 ru_utime+ru_stime of a child SIGKILLed at RLIMIT_CPU reads up to ~0.11 s below the limit under starvation; a `>= limit - 0.1` test flakes"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 485bcba65331c0cd
---

## wait4 ru_utime+ru_stime of a child SIGKILLed at RLIMIT_CPU reads up to ~0.11 s below the limit under starvation; a `>= limit - 0.1` test flakes

A child ended by RLIMIT_CPU (3, 3) dies by SIGKILL at the kernel's precise CPU
time, but `wait4`'s rusage is tick-sampled: six runs on one core with six
busy loops (load ~62) read 2.889 / 2.927 / 2.963 / 2.948 / 2.973 / 2.946 s.
`review-bash-guard.py` required `>= CPU_BUDGET_S - 0.1`, so one run in six
answered "error" instead of "slow" (j67 / j398).

**Why:** the figure is a measurement, not the limit; a tolerance sized for an
idle host is the same flake as a wall bound.
**How to apply:** compare a reported CPU figure to a fraction of the limit
(half), never to the limit minus a small constant; reproduce with
`taskset -c N` plus busy-loop burners on the same core before choosing the
bound. See [[silent-bounded-wait-before-signal-is-the-flake]] and
[[rlimit-cpu-equal-limits-sigkill-not-sigxcpu]].

*References: rlimit-cpu-equal-limits-sigkill-not-sigxcpu, silent-bounded-wait-before-signal-is-the-flake*

*Observed 2026-10-25 (python-dev)*
