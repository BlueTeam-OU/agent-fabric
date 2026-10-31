---
role: "python-dev"
class: domain
topic: "git-fixture-maintenance-lock"
description: a fixture git commit can start detached maintenance holding objects/maintenance.lock, so a before/after digest of the repo differs about once in thirty runs
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6cc4538104dc9592
---

## a fixture git commit can start detached maintenance holding objects/maintenance.lock, so a before/after digest of the repo differs about once in thirty runs

A test that digests a git repository before and after the code under test (a "nothing changed" assertion) failed about once in thirty parallel runs: `.git/objects/maintenance.lock` was in the first digest and gone in the second. The fixture's own `git commit` starts a detached `git maintenance run --auto`; it holds the lock for a moment. Found by snapshotting file hashes per run under load, not by reading the assertion.

**Why:** a flake that two reviewers each saw once and could not reproduce was the same race.
**How to apply:** every fixture helper that runs git passes `-c gc.auto=0 -c maintenance.auto=false` (tests/test_memory_check.py `git()` does since #213); when a digest assertion flakes, diff the per-file snapshot before guessing.

*Observed 2026-10-11 (python-dev)*
