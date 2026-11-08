---
role: "python-dev"
class: workflow
topic: "mode-arg-needs-preexisting-0644-file-and-fixture-copies-need-identity"
description: j96 conversion to identity writers — a 0600 mode argument is unobservable on a fresh file; fixture trees copying tools/fabric need runtime/identity.py
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f13a929f94ed21df
---

## j96 conversion to identity writers — a 0600 mode argument is unobservable on a fresh file; fixture trees copying tools/fabric need runtime/identity.py

Converting a write to `identity.atomic_write(path, data, 0o600)` / `append_line`:

- mkstemp already creates 0600, so a test of the `0o600` argument passes with the argument deleted. The mutation survives until the test pre-creates the target at 0644 under umask 022 and checks the mode after the write.
- Any test that copies `tools/fabric` into a tmp tree (test_launch, test_launch_cli, test_control_queue, test_gzcoord_i18n, test_query_cli) must now also copy `runtime/identity.py`, or the converted module fails on import.
- The ADR-003 scan over-reports whole modules; run it with the closed policy entries stripped, from a scratch script, never by editing the policy.

**Why:** three mutations survived in j96 (branch `for/user/j577-state-writes`) before the 0644 pre-creation, and four fixture trees broke after the conversion.
**How to apply:** for each converted write, plant "drop the mode argument" and read the rc; grep tests for `copytree`/`shutil.copy` of tools/fabric after touching imports. See [[shared-helper-module-three-traps]].

*References: shared-helper-module-three-traps*

*Anchors: `tests/test_identity_writers.py::0o644`*

*Observed 2026-11-07 (python-dev)*
