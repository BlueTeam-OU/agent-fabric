---
role: shared
class: threads
topic: "python-port-waves"
description: "The ADR-040 Python port is complete (all waves landed); the pinned interpreter is installed per host by python_pin.py"
tier: 2
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 92644fce5488ec2b
  - eb99b39175c70d71
---

## The ADR-040 Python port is complete (all waves landed); the pinned interpreter is installed per host by python_pin.py

Decided in agent-fabric ADR-040; read the record. All eight waves have landed and `policies/bash-allowlist.json` `scripts` is empty: bash remains only for shims, forwarders, hook entry points and suite runners, and the shims themselves are retiring for bare commands (rule 7).

The fleet's one Python is pinned in `runtime/python.json` (per-arch sha256) and installed once per host by `tools/fabric/python_pin.py install` (root, run by the host's own `/usr/bin/python3`; no bash step-runner, no `fabric-ctl all upgrade python`; upgrade pieces are `claude` and `fabric`). It is reached as `/usr/local/bin/fabric-python`.

Method invariants that still hold for any port: the script's path stays as a shim; the unchanged test is the parity oracle (and mutate each key behaviour, since an oracle misses band edges); the "why" comments move verbatim; read stdin only once argv needs it; never restore SIGPIPE's SIG_DFL in Python; a dispatch-hook shim must not exec (a failed hook reads as allow); strip GITHUB_* and AGENT_FABRIC_* in tests that call a guard in-process ([[run-suites-as-ci-before-push]]).

*References: run-suites-as-ci-before-push*

*Observed 2026-10-10 (fabric-coordinator)*
