---
role: "python-dev"
class: solution
topic: "j140-git-path-roots-merged"
description: "j140 #570 merged 2026-11-12 — roots.git_path/operator_prefix, base is the git toplevel; review traps and a CI flake"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cdffc9e3db569670
---

## j140 #570 merged 2026-11-12 — roots.git_path/operator_prefix, base is the git toplevel; review traps and a CI flake

#570 (ADR-045 precondition 5) merged ac9443ce: `roots.operator_prefix(base)` and `roots.git_path(*parts, base=)` answer the repository-relative path of a move-plan §1 item; `trust._main_show` uses them.

**Why the base is the toplevel:** `git show <rev>:<path>` spells the path from the repo top whatever `-C` names. With `fabric=None`, root is the operator dir itself, so base=root gave an empty prefix (review F1). Use `git rev-parse --show-toplevel`; operator_prefix uses realpath on both sides.

**How to apply:** `projects/` moves as registry.json, clients.json and project dirs, but `projects/schemas/` stays in the engine (F2). The coordinator's guards and CI steps must pass main's toplevel too, not the operator dir.

Traps: a PR touching trust.py/secretstore arms under 8 work only on the owner's word in the basis (`the owner's word`). platform-smoke debian once failed on test_control_agentd tokens `days` KeyError, unrelated; `gh run rerun --failed` passed. A new-test mutation with abspath instead of realpath is only caught if the operator is exported through a symlink.

*Anchors: `tools/fabric/roots.py::git_path`, `tools/fabric/secretstore/trust.py::_main_show`*

*Observed 2026-11-12 (python-dev)*
