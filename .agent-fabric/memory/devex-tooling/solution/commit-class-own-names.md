---
role: "devex-tooling"
class: solution
topic: "commit-class-own-names"
description: "commit_class reads \"word#N\" as this repository when the word is any name of the project holding the PR's owner/repo"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - daf12524dc9a6dfa
---

## commit_class reads "word#N" as this repository when the word is any name of the project holding the PR's owner/repo

tools/fabric/github/commit_class.py `own_names(here)`: a PR repository's own names are its repo name plus the
project id and every remote's name of each registered project whose remotes include owner/repo. `_ref` returns
"x" (another repository) only for a word that is registered and not among them. Cause: herdr#44 on
agent-fabric-fleetdeck#44 counted 3 review fixes as work (j149, REQUEST 01a150de, branch
develop-qzapp/devex-tooling/for/user/j149-commit-class-own-names, commit 39e817a2). A full owner/repo#N form
is still compared with the PR's repository and nothing else. The tests set AGENT_FABRIC_OPERATOR to a
fixture registry (tests/instance_fixtures.write_operator_projects), never the checkout's.

*Anchors: `tools/fabric/github/commit_class.py::own_names`*

*Observed 2026-10-18 (devex-tooling)*
