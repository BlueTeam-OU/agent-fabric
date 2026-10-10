---
role: "devex-tooling"
class: domain
topic: "github-actions-reusable-workflows"
description: "Inside a reusable workflow, github.event_name is the CALLING workflow's event; a gate that skips on an unlisted event can turn a release gate green with nothing built"
tier: 2
knowledge_scope: "domain-only"
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

## Inside a reusable workflow, github.event_name is the CALLING workflow's event; a gate that skips on an unlisted event can turn a release gate green with nothing built

Inside a reusable workflow (`on: workflow_call`), `github.event_name` is the CALLING workflow's event (`pull_request`, `merge_group`, `push`), never `workflow_call`. Gate a step on the caller's event, and pass anything the callee must branch on as an input.

A manual `workflow_dispatch` run of the caller (a release gate, say) arrives inside every child reusable workflow as `workflow_dispatch`, not as `push` or `merge_group`. A step gated on `github.event_name == 'merge_group' || github.event_name == 'push'`, a reasonable way to keep an expensive build to "real" triggers, silently skips on a manual dispatch; if the skip branch reports success (an echo or no-op step), the whole release gate goes green having never built the artifact it exists to verify. A condition that gates a step by event type enumerates every event that can reach the reusable workflow, manual dispatch of its caller included.

This is GitHub Actions behaviour, not a fabric decision, so it cites no ADR.

*Observed 2026-10-10 (devex-tooling)*
