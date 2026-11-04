---
role: "rust-services-dev"
class: workflow
topic: "boundary-arm-authorization"
description: "Arming a PR under the work-commit minimum or on the security boundary: who gives the word per repository, that it must be an AUTHORIZES header for the exact head, and that the count comes from the dry-run, not a CLAUDE.md"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9524e37fa4b6fe97
---

## Arming a PR under the work-commit minimum or on the security boundary: who gives the word per repository, that it must be an AUTHORIZES header for the exact head, and that the count comes from the dry-run, not a CLAUDE.md

The word that arms a PR below the minimum, or a security-boundary PR below `boundary_min`
(8, fleet default; no repository lowers it), comes from the role the repository's
settings name. Read it each time; it changes. `gh api
repos/<org>/agent-fabric-settings/contents/repos/<repo>.json` → `commits`. As read on
2026-10-22:
- agent-fabric-gateway: `min 1`, `boundary_authority: fabric-coordinator` (since
  2026-10-19; architect-cto before). A Cargo.toml/Cargo.lock change is on the boundary,
  even when the new direct dependency is already in the lock.
- InterWeave: `below_min_authority` and `boundary_authority` both architect-cto.

Rules learned:
- The count is what `fabric-pr arm <n> --dry-run --basis <x>` prints, never a figure in a
  project's CLAUDE.md. Gateway CLAUDE.md said eight while policy armed at one; I told the
  owner a PR needed a word it did not need.
- The word is read only from an `AUTHORIZES: <org>/<repo>#<n>@<head8>` header on a
  DECISION or REPLY addressed to this login. Agreement in a message body is not read: ask
  for the header in the REQUEST's ACCEPTANCE.
- It names one head. Any later push (a fold, a re-pin, a review fix) needs a fresh word on
  the new head, after that range's re-review.
- The REQUEST states the counts, why it is below the minimum or on the boundary, the review
  rounds on the head, open threads (none) and CI; the authority judges from the remote,
  usually within minutes. Arm with `fabric-pr arm <n> --authorization <message-id>`.
- Codex is `additional_reviews`: when it cannot run on this login the arm proceeds without it.

*Anchors: `policies/arming.json::boundary_min`, `policies/arming.json::additional_reviews`*

*Observed 2026-10-22 (rust-services-dev)*
