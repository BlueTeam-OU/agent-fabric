---
role: "python-dev"
class: workflow
topic: "stripped-two-files-j129"
description: "j129 #559 — stripped-copy fixes (env before import), post-review base ancestry, classifier denies post-review from the session"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2667caf1ca34e534
---

## j129 #559 — stripped-copy fixes (env before import), post-review base ancestry, classifier denies post-review from the session

- `runtime/claude-code/user-settings.py` computes AUTO_MODE_POLICY at import (line ~344): a test that wants a fixture policy sets `AGENT_FABRIC_OPERATOR` (`instance_fixtures.write_operator_policy`) BEFORE `load_script()`; setting it after still fails on a stripped copy.
- `fabric-pr post-review` refuses a report whose base is not an ancestor of the head: when main moved after the brief, merge origin/main, push, and re-brief on `origin/main..<new head>` (two dots; `fabric-review brief <req.yaml>`, `repository:` a local working-copy path).
- The auto-mode classifier denied `fabric-pr post-review` from the session as [Self-Approval]; the owner ran it with `!`. Ask for that up front when the owner has said "arm".
- Owner's "arm N" lifts the count only; the review of the head is still required, and an open P3 is lifted with `--defer "<head8>:F<n>" "<why>"`.
- A suite started in a background command that also lints/commits: the command's whole line runs in background, so the commit lands late; wait on it with an until-loop.

*Anchors: `runtime/claude-code/user-settings.py::AUTO_MODE_POLICY`*

*Observed 2026-11-11 (python-dev)*
