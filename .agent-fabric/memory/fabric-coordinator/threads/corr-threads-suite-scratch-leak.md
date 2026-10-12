---
role: "fabric-coordinator"
class: threads
topic: "corr-threads-suite-scratch-leak"
description: tests/run.sh owns a fresh TMPDIR per run and fails naming what is left in it; concurrent runs no longer share scratch
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dc3bfd878e623157
---

## tests/run.sh owns a fresh TMPDIR per run and fails naming what is left in it; concurrent runs no longer share scratch

A test run leaves behind nothing it did not find (ADR-021). `tests/run.sh` creates a fresh per-run directory (`SCRATCH_DIR`, exported as `TMPDIR`), fails naming each entry left in it and removes it on exit, so a second run, a pip install or an editor writing in the account's directory is never mistaken for a leak; `tests/leak-check.sh` is the check. The suites are Python and bash now (the Node suites and `tests/scratch.mjs` are gone): a Python test that needs state of its own imports `tests/isolated_state.py` (a throwaway `AGENT_FABRIC_STATE_DIR`, removed at process exit) and otherwise writes under `TMPDIR`.

**How to apply:** when run.sh names a leftover, fix the suite that made it at the rule level (a helper or an exit hook), never with a one-off `rm`. Two suites may run at once; a killed run's directory is the one thing to clean by hand.

*Observed 2026-10-11 (fabric-coordinator)*
