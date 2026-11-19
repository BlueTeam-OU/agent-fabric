---
role: "fabric-coordinator"
class: solution
topic: "mechanism-owner-may-be-package"
description: policies/mechanisms.json owner may be a package named dir/ (trailing slash); a checker or exceptions path stays a file
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2647773d58086b28
---

## policies/mechanisms.json owner may be a package named dir/ (trailing slash); a checker or exceptions path stays a file

`tools/fabric/lint_rules/mechanisms.py` took an entry's `owner` only as a tracked file, so job-lifecycle's owner
`tools/fabric/work/` (many modules) turned the imported-tree lint red (test_roots_readers, test_project_import) on the
suite run after 760d5a7b; the targeted tests and the tree's own lint stayed green. 58349d3d (#520): an owner ending in "/"
passes when a tracked file lies under it; checker and exceptions stay files. Wiring a new mechanism: run the full suite,
not only the mechanism's own tests, because the imported-tree cases are where the catalogue is judged.

*Anchors: `tools/fabric/lint_rules/mechanisms.py::_names_tracked`*

*Observed 2026-11-09 (fabric-coordinator)*
