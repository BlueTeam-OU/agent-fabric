---
role: "python-dev"
class: workflow
topic: "prefer-prs-with-more-than-one-work-commit"
description: owner asked for PRs carrying more than one work commit, so arming does not need their word each time
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c831765d8dea6281
---

## owner asked for PRs carrying more than one work commit, so arming does not need their word each time

After j97 (#503, 1 work commit, security-boundary file, armed on "arm 503"), the owner said: "try to create PRs with more commits than 1".

**Why:** a PR under the minimum (8 work commits; a boundary file such as tools/fabric/secretstore/trust.py has its own minimum) arms only on the owner's word or an AUTHORIZES decision, so each one-commit PR costs the owner a decision.

**How to apply:** while one PR of mine is open, further work is another commit on it (pull-requests skill); fold related findings of the same class into one PR as separate logical commits (fix, test, adjacent callers) rather than opening a PR per request. Read `fabric-pr arm <n> --dry-run --basis x` for the real minimum before asking.

*Anchors: `tools/fabric/secretstore/trust.py::_record_refusal_or_say`*

*Observed 2026-11-07 (python-dev)*
