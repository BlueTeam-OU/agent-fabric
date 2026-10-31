---
role: "python-dev"
class: domain
topic: "rlimit-cpu-equal-limits-sigkill-not-sigxcpu"
description: RLIMIT_CPU (n, n) kills the child with SIGKILL, not SIGXCPU; tell budget from OOM by wait4 rusage
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 23c0618201a43619
---

## RLIMIT_CPU (n, n) kills the child with SIGKILL, not SIGXCPU; tell budget from OOM by wait4 rusage

With `setrlimit(RLIMIT_CPU, (3, 3))` the kernel ends a spinning child by SIGKILL (soft == hard), never SIGXCPU; a pipe-reading parent sees EOF and no answer. Measured in j60 (review-bash-guard.py `judged()`). Read `os.wait4(pid, 0)` rusage: killed with ru_utime+ru_stime >= limit - 0.1 is the CPU budget, a kill with less CPU is something else (OOM) and stays an error. A hard limit above the soft one would make it SIGXCPU instead.

Testing a fork-based guard: set a stand-in `verdict` on the loaded module and call `judged()` directly; starve the child with SIGSTOP from a thread (child writes its pid to a file first). A full tests/run.sh can exceed the 30 min background cap when other logins' suites load the host: run the touched file alone and say so.

**Why:** the request assumed SIGXCPU; the check would have read "error" instead of "slow".
**How to apply:** any RLIMIT_CPU child with equal limits, and any wall-vs-CPU budget test.

*Observed 2026-10-22 (python-dev)*
