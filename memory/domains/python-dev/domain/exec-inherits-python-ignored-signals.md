---
role: "python-dev"
class: domain
topic: "exec-inherits-python-ignored-signals"
description: "a Python wrapper that os.exec's a command, or a test that probes signal dispositions — SIGPIPE/SIGXFSZ are SIG_IGN after Python start-up"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a8a93f169777202a
---

## a Python wrapper that os.exec's a command, or a test that probes signal dispositions — SIGPIPE/SIGXFSZ are SIG_IGN after Python start-up

CPython sets SIGPIPE and SIGXFSZ to SIG_IGN at start-up. subprocess restores
them in the child (restore_signals=True), but os.execve keeps an ignored
disposition, so a Python wrapper that becomes the command hands it ignored
SIGPIPE unless it resets them — and the caller's own ignored state is lost,
so the bash shim must hand it over (bin/fabric-secret-run exports
_FABRIC_SECRET_RUN_IGNORED from `trap -p PIPE/XFSZ`; tools/fabric/secret_run.py
restores, as bin/fabric-lease does for PIPE).
Testing it: a Python probe reports SIG_IGN whatever it was given (its own
start-up set it). Probe with `cat /proc/self/status` and read the SigIgn mask
(bit signum-1). Seen on agent-fabric j49, tests/test_fabric_secret_run_cli.py.
Related: [[python-defaults-that-differ-from-node]].

*References: python-defaults-that-differ-from-node*

*Observed 2026-10-07 (python-dev)*
