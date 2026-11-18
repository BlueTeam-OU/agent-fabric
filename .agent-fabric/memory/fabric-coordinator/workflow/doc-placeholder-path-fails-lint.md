---
role: "fabric-coordinator"
class: workflow
topic: "doc-placeholder-path-fails-lint"
description: "a placeholder path in an agent-fabric doc (docs/adr/history/ADR-NNN-amendments.md) is a lint finding, and it reddens test_roots_readers and test_project_import too"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5b167b2721351558
---

## a placeholder path in an agent-fabric doc (docs/adr/history/ADR-NNN-amendments.md) is a lint finding, and it reddens test_roots_readers and test_project_import too

In agent-fabric docs, a path-shaped placeholder that names no real file is a citation lint finding: "cites docs/adr/history/ADR-NNN-amendments.md, which does not exist". It turns red not only corpus lint but also tests/test_roots_readers.py and tests/test_project_import.py, because both assert that lint on a copy of the tree is clean. Seen on #557 at b60ea52a (j725). A glob (`docs/adr/ADR-NNN-*.md`) passed. The fix was a shell variable: `docs/adr/history/"$r"-amendments.md`.

**Why:** the docs lint resolves every repository path it finds in prose and code blocks alike.
**How to apply:** in a plan's command block, write placeholders as `$VAR` or `<name>`, never as a literal path shape. When three suites go red after a docs-only commit, read the corpus lint diff against the previous run first. Related: [[tests-and-suite]].

*References: tests-and-suite*

*Anchors: `tools/fabric/lint_rules/docs.py::which does not exist`, `tests/test_roots_readers.py::lint without an operator is not clean`*

*Observed 2026-11-11 (fabric-coordinator)*
