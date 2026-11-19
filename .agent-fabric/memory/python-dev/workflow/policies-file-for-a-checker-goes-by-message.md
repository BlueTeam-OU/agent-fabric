---
role: "python-dev"
class: workflow
topic: "policies-file-for-a-checker-goes-by-message"
description: "the exceptions file of a ADR-067 checker (policies/*.json) cannot be committed by python-dev even on a for/user branch; send it in the reply"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 798c0ac0df540834
---

## the exceptions file of a ADR-067 checker (policies/*.json) cannot be committed by python-dev even on a for/user branch; send it in the reply

The commit hook refuses `policies/work-writes.json` on `develop-qzapp/python-dev-04/for/user/...` ("outside what python-dev commits here"); j125's process-spawns.json was likewise written by fabric-coordinator. The REQUEST's "deliver it on a for/ branch" cannot be done.

**How to apply:** build the checker and its test (the test can carry the exceptions inline and run the real tree with and without them), and put the file's content in the REPLY to the requester with the wiring that is theirs. Say so before spending a worktree on it.

*Observed 2026-11-09 (python-dev)*
