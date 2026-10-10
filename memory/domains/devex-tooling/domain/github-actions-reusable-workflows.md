---
role: "devex-tooling"
class: domain
topic: "github-actions-reusable-workflows"
description: "correction — the reusable-workflow event_name slice cites ADR-047, which is unrelated (Plans); drop the reference"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
  - clone_id: "clone-948c9fcd4da94057"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 0eb9458052405327
  - 2d508d12807af565
  - 6f76e2f75e9f7e7f
  - b00c726f217a6d52
---

## correction — the reusable-workflow event_name slice cites ADR-047, which is unrelated (Plans); drop the reference

Inside a reusable workflow (`on: workflow_call`), `github.event_name` is the CALLING workflow's event (`pull_request`, `merge_group`, `push`), never `workflow_call`. Gate a step on the caller's event, and pass anything the callee must branch on as an input.

This is GitHub Actions behaviour, not a fabric decision, so it cites no ADR. agent-fabric ADR-047 is about plans the coordinator keeps and does not apply.

*Observed 2026-10-10 (devex-tooling)*
