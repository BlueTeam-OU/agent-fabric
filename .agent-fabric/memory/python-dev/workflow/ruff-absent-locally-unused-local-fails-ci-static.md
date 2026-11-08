---
role: "python-dev"
class: workflow
topic: "ruff-absent-locally-unused-local-fails-ci-static"
description: "ruff is not installed in the sandbox, so an unused local in a new test passes every local suite and fails CI static (F841); a one-line fix push then needs its own re-review"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d834837cb8283f5c
---

## ruff is not installed in the sandbox, so an unused local in a new test passes every local suite and fails CI static (F841); a one-line fix push then needs its own re-review

j84 / #448: a leftover `reused = claim(...)` in a new test passed `tests/run.sh`
and lint.py locally; CI `static` (ruff F841) failed, and `platform-smoke` ran the
same static step. `ruff` and `pyflakes` are not importable here.

**Why:** the local suite does not include ruff, so green locally says nothing of
unused names.

**How to apply:** before the first push of a new test, scan its locals with a
short `ast` script (assigned names never loaded) instead of trusting the suite.
A fix push after a clean review moves the head, and the gate then wants a
re-review of that range (`fabric-review next` with the request's range pinned
as full shas and `--head` as a full sha; 12 characters are refused). Related:
[[review-report-post-extract-from-transcript]].

*References: review-report-post-extract-from-transcript*

*Anchors: `tests/static.sh::ruff`*

*Observed 2026-11-01 (python-dev)*
