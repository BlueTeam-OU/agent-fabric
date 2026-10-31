---
role: "web-dev"
class: workflow
topic: "agent-store-writes-via-settings-put"
description: "How to put files (persona, avatar) into my own fabric-agent-<id> repository — never by cloning it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 62a88d7ab045c0eb
---

## How to put files (persona, avatar) into my own fabric-agent-<id> repository — never by cloning it

My `BlueTeam-OU/fabric-agent-<id>` repository is my secrets store (ADR-038). It is written only
through `fabric-secrets store settings-put --from <dir>`: that makes one signed commit, verified on
pull (ADR-042), and pushes it. The dir is laid out the way `settings/` will be. Cloning or pushing
the store by hand gets refused by the permission check, and that refusal is correct. Ten agents
hand-pushed their avatar commits on 2026-10-13, and the coordinator rolled them back.

The command prints "settings: N file(s) committed" and no sha. The coordinator said that line is
enough evidence. It also said never to read the store's git log by hand to find the sha
(broadcast 01a136de, 2026-10-13).

**Why:** a command your safety check refused is a finding, never a task for the owner. I once asked
the owner to allow the clone; the right move was to wait for the store's own tool.

**How to apply:** for anything that belongs in `settings/`, stage it in the scratchpad and run
settings-put. If no tool exists for it yet, block the job "on <tool>", not on the owner.

*Anchors: `tools/fabric/secretstore/settings.py::settings_put`*

*Observed 2026-10-15 (web-dev)*
