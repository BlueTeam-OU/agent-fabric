---
role: "fabric-coordinator"
class: workflow
topic: "lint-before-commit"
description: "Run lint.py --no-siblings and, for an ADR edit, fabric-adr range-check before every agent-fabric commit"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 20d98f61b52e1ac2
  - 6e610317df333b6e
  - 9c1a02eb83b2e02b
---

## Run lint.py --no-siblings and, for an ADR edit, fabric-adr range-check before every agent-fabric commit

Before committing in agent-fabric: `env -u AGENT_FABRIC_ROOT python3 tools/fabric/lint.py --no-siblings`, capture rc, commit only on 0. The suites and `tests/run.sh static` do not run the corpus lint, and lint refuses a project name in a generic file; it caught one three times after the commit (2026-09-27), each costing a fix commit.

A commit that edits an ADR body also runs `fabric-adr range-check` before the push (CI's base..head, else `AGENT_FABRIC_ADR_BASE`, else origin/main..HEAD; `policies/check_adr_amendment.sh` is a retiring forwarder to it, and `tests/run.sh` runs it as "decision-record amendments (this branch)"). A clarifying row pushed without the suite and without an `ADR-Editorial:` trailer turned two CI legs red (2026-10-04).

**How to apply:** one command line per commit: lint, the touched suite, then `git commit`, each status captured ([[check-exit-status-not-pipe]]).

*References: check-exit-status-not-pipe*

*Observed 2026-10-10 (fabric-coordinator)*
