---
role: "python-dev"
class: solution
topic: "shared-helper-module-three-traps"
description: "Adding a new tools/fabric module that jobs parts or fixtures load: fixture copy lists, project names in docstrings, frozen-oracle texts"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4e4a05924f43e5fb
---

## Adding a new tools/fabric module that jobs parts or fixtures load: fixture copy lists, project names in docstrings, frozen-oracle texts

j68 (PR 377) put the registry-id grammar in `tools/fabric/registry_id.py`. Three things only the full suite or lint showed:

- `tests/test_launch_cli.py` builds a fixture fabric from a hand-kept file list (jobs.py plus copytree of jobsparts): a file the parts load by path must be added to that list, or jobs.py dies at import with FileNotFoundError.
- `lint.py --no-siblings` (run by test_roots_readers and the import --like cases) flags a managed project's name (e.g. a dotted registry id) in any generic tool file's docstring; plain `lint.py` does not. Say "a brand or locale id", never the id.
- A test that reads the checkout's `projects/registry.json` needs an entry in `DELIBERATE` in tests/test_tests_read_fixtures.py. And control/jobs.py's refusal text is frozen by tests/test_control_jobs.py's Node oracle: widening a grammar must not reword it.
- Tests run in the session env resolve `control` from the main checkout (AGENT_FABRIC_ROOT): run suites with AGENT_FABRIC_*/GITHUB_*/GIT_DIR unset or imports test the wrong tree.

**Why:** each cost a full-suite cycle (~25 min) after the change looked done.
**How to apply:** before the first full run, grep tests for the copy list of the module's neighbours, run `lint.py --no-siblings`, and unset the env.

*Anchors: `tools/fabric/registry_id.py`, `tests/test_launch_cli.py`, `tests/test_tests_read_fixtures.py`*

*Observed 2026-10-25 (python-dev)*
