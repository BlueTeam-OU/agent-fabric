---
role: shared
class: threads
topic: "suite-scratch-leak"
description: tests/run.sh owns a fresh TMPDIR per run and fails naming what is left in it; concurrent runs no longer share scratch
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
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 348871f287af9d15
  - d1814b604dc786fb
---

## tests/run.sh owns a fresh TMPDIR per run and fails naming what is left in it; concurrent runs no longer share scratch

A test run leaves behind nothing it did not find (ADR-021). `tests/run.sh` creates a fresh per-run directory (`SCRATCH_DIR`, exported as `TMPDIR`), fails naming each entry left in it and removes it on exit, so a second run, a pip install or an editor writing in the account's directory is never mistaken for a leak; `tests/leak-check.sh` is the check. Node suites use `tests/scratch.mjs` (removed at process exit) and `tests/static.sh` refuses inline `mkdtempSync` in a `*.test.mjs`.

**How to apply:** when run.sh names a leftover, fix the suite that made it at the rule level (a helper or an exit hook), never with a one-off `rm`. Two suites may run at once; a killed run's directory is the one thing to clean by hand.

*Observed 2026-10-10 (fabric-coordinator)*
