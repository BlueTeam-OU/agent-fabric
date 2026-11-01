---
role: "python-dev"
class: workflow
topic: "helper-body-was-a-self-call"
description: "a scripted extract-helper left a function whose whole body called itself; tests patching the helper hid it from 50 green runs"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 19164e9ca7624faf
---

## a scripted extract-helper left a function whose whole body called itself; tests patching the helper hid it from 50 green runs

In #413 (repo-policy apply) `_registry_and_clients` shipped with its body a call to itself: RecursionError on every real plan/verify/apply, while every test patched the helper. Review found it (F5/F6); fixed in 5a0851c1 with `load_with_source` (one fetch decides source and policy) and tests that patch only the registry and file reads.

**Why:** a test that mocks the unit under extraction can never run it.
**How to apply:** after extracting a helper, run one test with no mock on it and run the real command once; patch the boundary below the helper. See [[j182-self-call-and-job-guard-oscillation]].

Follow-up: devex-tooling saw apply's read-back GET return pre-PATCH values (stale read, exit 1 on a correct write) — j183.

*References: j182-self-call-and-job-guard-oscillation*

*Observed 2026-10-28 (python-dev)*
