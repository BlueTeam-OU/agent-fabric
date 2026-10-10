---
role: "fabric-coordinator"
class: workflow
topic: "commands-for-the-owner-bare-names"
description: "A command given to the owner (or in a person-facing hint) is the bare PATH name, never bin/<cmd>"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0ff8130ca336fc40
---

## A command given to the owner (or in a person-facing hint) is the bare PATH name, never bin/<cmd>

A command handed to a person — in a reply, a `!` line, an error hint, a locale string — names the command as it is on PATH (`fabric-secrets`, `fabric-ctl`, `fabric-accounts`, `fabric-tools`), never `bin/fabric-…`, which works only from the agent-fabric checkout.

**Why:** the owner, 2026-10-08: "this path is not folder idempotent" about my `bin/fabric-secrets store put …` line; rust-ui-dev-01 found the same in websearch-locale/server.mjs, the gzcoord i18n token hints, agentd.mjs and three docs (seq 20597).

**How to apply:** `~/.local/bin/` holds a symlink per command (bootstrap); use the bare name for people, `bin/…` only inside code and tests that run from the checkout.

*Observed 2026-10-08 (fabric-coordinator)*
