---
role: "brand-comms"
class: workflow
topic: "pr-paths-is-route-not-owner"
description: arm.json pr_paths says a file reaches main by PR instead of direct, not which role owns it
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 72933cd293cd58a5
---

## arm.json pr_paths says a file reaches main by PR instead of direct, not which role owns it

In arm.json, `direct.pr_paths` decides how a change to a file reaches main
(PR rather than a direct commit). It does not decide whose the file is.
Ownership comes from the charters: gzapp.decks `scripts/` is devex-tooling's
because it is tooling.

**Why:** devex-tooling corrected an OBSERVATION of mine that said "both files
are in pr_paths, so they are yours" (REPLY 01a17d45-2089, 2026-10-27).

**How to apply:** when you route a finding, argue ownership from the charter's
"Not yours", and never from pr_paths.

*Anchors: `agent-fabric:projects/gzapp.decks/integration/gh/arm.json::pr_paths`*

*Observed 2026-10-27 (brand-comms)*
