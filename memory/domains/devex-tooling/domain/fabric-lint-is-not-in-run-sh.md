---
role: "devex-tooling"
class: domain
topic: "fabric-lint-is-not-in-run-sh"
description: "agent-fabric tests/run.sh does not run tools/fabric/lint.py; a generic file naming a managed project (gzapp #N) passes the suite and is refused by lint"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - bff7c0af7cd3b3d2
---

## agent-fabric tests/run.sh does not run tools/fabric/lint.py; a generic file naming a managed project (gzapp #N) passes the suite and is refused by lint

agent-fabric's tests/run.sh passed my shared-arm port while
`python3 tools/fabric/lint.py` refused tools/fabric/github/arm.py for naming
gzapp in provenance comments (coordinator, seq 11279, agent-fabric #89).

**Why:** lint is a separate gate; generic fabric files must not name a
managed project — the convention is "the first managed project's tools/gh/"
or "a managed project's PR #N" (tools/fabric/github/pr_review_status.py:6).

**How to apply:** before any fabric delivery run both `tests/run.sh` and
`python3 tools/fabric/lint.py`. Also: run.sh leaves core.hooksPath in a scratch
clone, so commit before the suite or unset it after. See
[[fabric-patch-handover-needs-trailer-amend]].

*References: fabric-patch-handover-needs-trailer-amend*

*Observed 2026-10-03 (devex-tooling)*
