---
role: "fabric-coordinator"
class: workflow
topic: "test-brief-host-state"
description: A brief for supplied tests names every account or host input the test must fixture (live policy and routing files, git signing config and version, sibling checkouts, token files, process scans), a scratch env with PYTHONDONTWRITEBYTECODE…
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fe52f7d5e4d73210
---

## A brief for supplied tests names every account or host input the test must fixture (live policy and routing files, git signing config and version, sibling checkouts, token files, process scans), a scratch env with PYTHONDONTWRITEBYTECODE, and the mutation to plant and run

Reviews kept finding supplied tests that passed on the author's account and failed on CI or another login: a live policy file read instead of a fixture, the runner's gitconfig, sibling checkouts changing a warning count, a bridge-token file, a hyphen-less login, `__pycache__` written into the tree, git 2.47 versus 2.56 behaviour and wording. Others asserted something that matched 16 places, so the named mutation survived.

**Why:** a test that depends on who runs it proves nothing on the next account.
**How to apply:** the brief lists each host or account input and says the test fixtures it, builds its env from scratch with PYTHONDONTWRITEBYTECODE=1, avoids git-version-specific output, and plants the mutation it claims to catch. Check whether `tests/test_tests_read_fixtures.py` can enforce a case before writing it into a brief. Related: [[new-test-own-tree-and-scratch]], [[hook-fixtures-copy-module-list]].

*References: hook-fixtures-copy-module-list, new-test-own-tree-and-scratch*

*Observed 2026-10-22 (fabric-coordinator)*
