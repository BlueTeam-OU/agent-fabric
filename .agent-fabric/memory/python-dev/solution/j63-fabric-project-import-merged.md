---
role: "python-dev"
class: solution
topic: "j63-fabric-project-import-merged"
description: "fabric-project import (#306 merged) — what it does, what coordinator still owes, traps met building and reviewing it"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8c75d98ee8cefe30
---

## fabric-project import (#306 merged) — what it does, what coordinator still owes, traps met building and reviewing it

`bin/fabric-project import` (tools/fabric/project.py, tests/test_project_import.py) merged as BlueTeam-OU/agent-fabric#306 on 2026-10-19; reply sent to develop-qzapp/user (request 01a15192).

**Still owed by fabric-coordinator (outside python-dev's entry):** SKILL.md repo-lifecycle §B steps 2-4 + "Not automated yet" line, runtime/claude-code/commands.json, policies/auto-mode.json CLI list.

**Why / traps (how to apply next time):**
- registry.json is hand-formatted (inline tools lists): insert the new entry as text after the last project and re-parse to compare; never re-dump.
- Compare remotes with `workingcopy.canonical_remote` (ports, case, ssh/https), never a home-made key: review P2 was an entry shadowed behind a registered one.
- `tests/test_roots_seam.py` flags `os.path.join(root, "projects", ...)`: use `roots.projects_registry/clients_registry/role_catalog/project_integration(root=root)`.
- A test that copies the live tree needs a DELIBERATE entry in tests/test_tests_read_fixtures.py and a skip when the registry is absent (stripped copy); verify with tests/stripped_run.py.
- Imports in a dry run write `__pycache__`: set `sys.dont_write_bytecode` before imports.
- lint `arm_declared_findings` reads git-tracked files: a test must `git add -A` the imported tree before linting it.
- CI `static` runs ruff: unused import failed platform-smoke and static; run tests/static.sh before pushing.
- A symlink check must cover every ancestor directory of a planned file (class), not the two levels named; the reviewer found a level deeper twice.
- Re-review brief needs `card_base:` (first round's base) when the range base is a branch commit.

*Anchors: `tools/fabric/project.py::canonical_remote`, `tests/test_project_import.py::tree-moved`*

*Observed 2026-10-19 (python-dev)*
