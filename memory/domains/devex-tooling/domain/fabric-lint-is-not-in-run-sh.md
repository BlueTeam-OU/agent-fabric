---
role: "devex-tooling"
class: domain
topic: "fabric-lint-is-not-in-run-sh"
description: "correction — agent-fabric tests/run.sh does run tools/fabric/lint.py (\"corpus lint\"); only a narrower section skips it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - bff7c0af7cd3b3d2
  - c7f6d6a9781c1d41
---

## correction — agent-fabric tests/run.sh does run tools/fabric/lint.py ("corpus lint"); only a narrower section skips it

agent-fabric's `tests/run.sh` runs `tools/fabric/lint.py` as "corpus lint" in its `python` section, which the default (`all`) includes. Only a narrower section (`bash`, `static`) skips it. Before a fabric delivery, run the full suite, or the `python` section plus whatever else changed, not a subset.

The rule the lint enforces still holds: a generic fabric file must not name a managed project. Write "the first managed project's tools/gh/", never "gzapp #N".

*Observed 2026-10-10 (devex-tooling)*
