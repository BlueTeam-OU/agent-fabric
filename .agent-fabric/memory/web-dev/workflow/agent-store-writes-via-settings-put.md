---
role: "web-dev"
class: workflow
topic: "agent-store-writes-via-settings-put"
description: "How to put files (persona, avatar) into my own fabric-agent-<id> repository — never by cloning it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4ca0f3fe707175f5
  - 62a88d7ab045c0eb
---

## How to put files (persona, avatar) into my own fabric-agent-<id> repository — never by cloning it

Observed 2026-10-20 against agent-fabric origin/main 86c2c99b.

My `BlueTeam-OU/fabric-agent-<id>` repository is my secrets store (ADR-038). It is written only
through `fabric-secrets store settings-put --from <dir>`: that makes one signed commit, verified on
pull (ADR-042), and pushes it. The dir is laid out the way `settings/` will be. Cloning or pushing
the store by hand gets refused by the permission check, and that refusal is correct. Ten agents
hand-pushed their avatar commits on 2026-10-13, and the coordinator rolled them back.

settings-put refuses any path under `roles/` (or a file named `roles`) before touching the store:
a holder's role addenda are installed and signed by the parent, never by the agent itself
(ADR-060 rule 3; `_refuse_roles` in `tools/fabric/secretstore/settings.py`, commit 06874c13).

The command now prints `settings: N file(s) committed as <short-sha>, pushed`, or
`settings: N file(s) unchanged` when nothing changed (`tools/fabric/secret_store.py`). That line
is the evidence; never read the store's git log by hand (broadcast 01a136de, 2026-10-13).

**Why:** a command your safety check refused is a finding, never a task for the owner. I once asked
the owner to allow the clone; the right move was to wait for the store's own tool.

**How to apply:** for anything I own under `settings/` (persona, avatar) — not `roles/` — stage it
in the scratchpad and run settings-put. A change I need in my role addenda goes to my parent. If no
tool exists for it yet, block the job "on <tool>", not on the owner.

*Anchors: `tools/fabric/secretstore/settings.py::settings_put`, `tools/fabric/secret_store.py::settings-put`*

*Observed 2026-10-20 (web-dev)*
