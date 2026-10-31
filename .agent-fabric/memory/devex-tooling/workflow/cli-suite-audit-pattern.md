---
role: "devex-tooling"
class: workflow
topic: "cli-suite-audit-pattern"
description: "how to cut a slow agent-fabric CLI test suite to smoke cases without losing a contract, and the trap a blind review caught"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6d12b29042a1f68a
---

## how to cut a slow agent-fabric CLI test suite to smoke cases without losing a contract, and the trap a blind review caught

Cutting a `tests/test_*_cli.py` suite (agent-fabric j95, branch develop-qzapp/devex-tooling/for/user/cli-suite-audit, 2026-10-12):
five PR-tooling suites went 153.7 s → 30.5 s serial by keeping one subprocess run per process-level outcome
(exit status, stream, output mode, usage refusal, gh failure, PATH/env/cwd behaviour) and driving the rest
in-process through the module's `run()`/`main()` with gh's functions patched and restored in `finally`.

The trap: an in-process replacement that fakes the very function a removed CLI case exercised keeps the
decision but loses the read. Review P2-1: the unit cases faked `local.remote_url`, so nothing read a real
clone's `origin` any more; a `remote_url` answering "" passed every suite. Fix: one case per caller that leaves
the reader real against a throwaway `git init` + `remote add origin` repo. Before removing a CLI case, list the
module functions the unit fake replaces and keep one real call for each.

Where the unit twin is another role's file (arm: test_arm_policy is not devex-tooling's), the cases convert
in-process inside the CLI file itself rather than move. A mutation check need not edit product code:
patch the function in memory and `runpy.run_path` the suite (an on-disk sed of product code was refused by
the auto-mode classifier).

Related: [[gzcoord-compose-test-login-trap]]

*References: gzcoord-compose-test-login-trap*

*Observed 2026-10-11 (devex-tooling)*
