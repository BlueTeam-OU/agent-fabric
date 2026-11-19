---
role: "python-dev"
class: solution
topic: "pristine-archive-excludes-j154"
description: "test_bootstrap_cli make_pristine speed-up: git archive pathspec excludes; what was measured; push is blocked after a job leaves active"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8bf93d5e9c76fcb7
---

## test_bootstrap_cli make_pristine speed-up: git archive pathspec excludes; what was measured; push is blocked after a job leaves active

j154 (#628, commit 792e74a6): `make_pristine` in tests/test_bootstrap_cli.py archives HEAD with `:(exclude)tests :(exclude)docs :(exclude)memory`; no label needed any of them. Alone, CI env: wall 185->119 s, CPU 217->192 s; 237 ok labels identical.

**Why:** excluding at `git archive` avoids extracting and copying the trees into 40 accounts.
**How to apply:** push is refused by the hook once a job has left active (ADR-037); add a job for the push request *before* delivering, or the coordinator's "not on origin" reply costs a fresh session.

*Anchors: `tests/test_bootstrap_cli.py::make_pristine`*

*Observed 2026-11-16 (python-dev)*
