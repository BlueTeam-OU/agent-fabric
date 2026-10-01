---
role: "fabric-coordinator"
class: workflow
topic: "lint-before-commit"
description: "Run tools/fabric/lint.py --no-siblings before every agent-fabric commit, not only the suites — lint caught a project name in a generic file three times after the commit (2026-09-27)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 20d98f61b52e1ac2
---

## Run tools/fabric/lint.py --no-siblings before every agent-fabric commit, not only the suites — lint caught a project name in a generic file three times after the commit (2026-09-27)

Before committing in agent-fabric: `env -u AGENT_FABRIC_ROOT python3
tools/fabric/lint.py --no-siblings`, capture rc, commit only on 0 — the
suites and `tests/run.sh static` do not run the corpus lint.

**Why:** on 2026-09-27 a comment naming a managed project reached a commit
three times (the launcher's working-copy block, commit-class.sh twice'
wording) because only tests and static ran; lint refuses a project name
in a generic file and caught each one afterwards, costing a fix commit.

**How to apply:** one command line per commit: lint, the touched suite,
then `git commit`, each status captured ([[check-exit-status-not-pipe]]).

*References: check-exit-status-not-pipe*

*Observed 2026-09-27 (fabric-coordinator)*
