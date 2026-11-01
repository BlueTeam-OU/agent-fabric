---
role: "devex-tooling"
class: workflow
topic: "generic-file-names-no-project"
description: "agent-fabric lint refuses a managed project's name (herdr, gzapp, …) in a generic file's comments; say \"<id>\" or describe it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8af5d23c5f65bf51
---

## agent-fabric lint refuses a managed project's name (herdr, gzapp, …) in a generic file's comments; say "<id>" or describe it

`tools/fabric/lint.py` flags "names a managed project ('<id>') in a generic file" for a project id anywhere in
tools/ code, docstrings and comments included. Tests may name them. It also fails test_roots_readers'
"lint without an operator" case, so one stray name costs two suites. Caught on j149 (commit_class own_names
docstring citing the incident by project name).
**Why:** project truth belongs in projects/<id>/ or the project's .agent-fabric/ remit, never generic code.
**How to apply:** cite the incident by REQUEST id and shape ("<id>#44 on a renamed repository"), and run
`python3 tools/fabric/lint.py --no-siblings` before the commit, not only after the suite. See [[lint-no-siblings-for-own-tree]].

*References: lint-no-siblings-for-own-tree*

*Anchors: `tools/fabric/lint.py::in a generic file`*

*Observed 2026-10-18 (devex-tooling)*
