---
role: "python-dev"
class: workflow
topic: "assembler-comments-must-not-name-the-project"
description: "tools/ comments citing a drain by its managed project's name fail test_roots_readers; and the seams runner dies on a KeyError so controls need a per-test loop"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 78c1f18690d97106
---

## tools/ comments citing a drain by its managed project's name fail test_roots_readers; and the seams runner dies on a KeyError so controls need a per-test loop

Writing "with this run as the case" (ADR-015) in `tools/fabric/assembler/` must not name the managed project (InterWeave): the corpus lint flags "names a managed project in a generic file" and only `tests/test_roots_readers.py` + `test_project_import.py` show it (j481, 2026-10-31). Say "a project's drain of <date> (jNNN)".

**Why:** found only by the full `tests/run.sh`, after assemble tests were green.
**How to apply:** grep the diff of tools/ for project names before the first full run. For base controls, run each new test in a loop catching BaseException on a detached worktree of origin/main: `test_assemble_seams.py`'s own runner stops at a KeyError and hides the later cases.

*Observed 2026-10-31 (python-dev)*
