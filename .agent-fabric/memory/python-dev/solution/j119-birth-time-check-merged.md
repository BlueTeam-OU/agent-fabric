---
role: "python-dev"
class: solution
topic: "j119-birth-time-check-merged"
description: "j119 — stripped nightly flaky birth-time check was the test's own date %3N reading, not the id; PR 495 merged 8bee04b3"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f07261f566597a73
---

## j119 — stripped nightly flaky birth-time check was the test's own date %3N reading, not the id; PR 495 merged 8bee04b3

The check "its id's time is its home's creation time" in tests/test_store_enroll_cli.py failed ~1 in 10 stripped nightlies because its reference `date -d <stamp> +%s%3N` misreads a stat `%w` fraction that begins with a zero on CI's coreutils (.005186207 gave 518, .054 gave 549); local coreutils 9.7 is fine. The id minting was correct. Fixed in PR 495 (8bee04b3): `stamp_ms` reads the first three fraction digits as text; tests/stripped_run.py `failing_lines` keeps a failing check's detail lines.

**Why:** a flake with a 10% rate looked unreproducible locally; only the logged values (id vs reference) showed the reference was wrong.
**How to apply:** when a check compares against a host tool's output, log both sides in the detail; dispatch ~10 nightlies in parallel (workflow_dispatch, concurrency group is per run) to catch a 10% flake. A mutant that survives may be a sample text containing the keyword the code matches (my "FAIL" in a detail line). Arm minimum in agent-fabric is 1 work commit, so own PRs arm after review.

*Anchors: `tests/test_store_enroll_cli.py::stamp_ms`, `tests/stripped_run.py::failing_lines`*

*Observed 2026-11-05 (python-dev)*
