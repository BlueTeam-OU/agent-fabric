---
role: "python-dev"
class: solution
topic: "stripped-operator-fixture-j63"
description: "j63 — a tool that finds a project's settings repo through registry/clients fails on a stripped copy; fix is a fixture operator tree via AGENT_FABRIC_OPERATOR"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1a8dfa61c4c634a7
---

## j63 — a tool that finds a project's settings repo through registry/clients fails on a stripped copy; fix is a fixture operator tree via AGENT_FABRIC_OPERATOR

tests/test_repo_settings_cli.py (j63, branch develop-qzapp/python-dev-03/feat/j63-stripped-nightly-red-tests-test-repo, 3989515b): the default repo's policy is found via arm_policy.load -> workingcopy.load_registry + operator projects/clients.json. On a stripped copy no project owns the repo, so cases fail. Fix: write registry.json + clients.json (settings_repo BlueTeam-OU/agent-fabric-settings) in a temp operator tree, export AGENT_FABRIC_OPERATOR in the tool's env (test strips AGENT_FABRIC_* so it must be re-added). Mutations: wrong settings_repo, or dropping the export, each fail the two policy cases.

**Trap:** a sed mutation restored from a backup path that did not exist left the mutated file in place; check with cmp before committing.
**Push:** plain git push has no credentials; use `-c credential.helper='!gh auth git-credential'`.

*Anchors: `tests/test_repo_settings_cli.py::AGENT_FABRIC_OPERATOR`*

*Observed 2026-10-19 (python-dev)*
