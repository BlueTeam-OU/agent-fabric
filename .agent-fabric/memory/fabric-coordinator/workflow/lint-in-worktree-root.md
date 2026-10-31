---
role: "fabric-coordinator"
class: workflow
topic: "lint-in-worktree-root"
description: "Running tools/fabric/lint.py inside a worktree without AGENT_FABRIC_ROOT=$PWD judged the main checkout, so a branch's schema finding went unseen and CI's platform-smoke went red"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4fe5d693a18e09a6
---

## Running tools/fabric/lint.py inside a worktree without AGENT_FABRIC_ROOT=$PWD judged the main checkout, so a branch's schema finding went unseen and CI's platform-smoke went red

2026-10-13, #238: I linted my branch's worktree (scratchpad clone) with plain
`python3 tools/fabric/lint.py` and saw nothing, yet the branch's new
identities/schemas/persona-profile.schema.json carried `"format": "date"`, a keyword the fallback
validator does not check (schema.py SCHEMA_KEYWORDS), which the corpus lint refuses on stderr.
`AGENT_FABRIC_ROOT=$PWD python3 tools/fabric/lint.py --no-siblings` in the worktree shows it.
Only the platform-smoke (debian/fedora) jobs run the corpus lint; the ubuntu guards-and-suites jobs
do not, and tests/test_roots_readers.py reports the failure as `'' vs ''` (it prints stdout only).

**Why:** lint resolves the fabric root from the environment/checkout layout, not the cwd.
**How to apply:** lint a branch with AGENT_FABRIC_ROOT=$PWD from its own tree before pushing; a
schema uses only keywords in SCHEMA_KEYWORDS (a `pattern`, not `format`).

*Observed 2026-10-13 (fabric-coordinator)*
