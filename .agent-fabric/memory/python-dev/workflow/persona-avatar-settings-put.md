---
role: "python-dev"
class: workflow
topic: "persona-avatar-settings-put"
description: "how an agent commits its ADR-056 persona (profile.json + avatar.png) with fabric-secrets store settings-put"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric-fleet"
derived_from:
  - e6187d06c8cadc0a
---

## how an agent commits its ADR-056 persona (profile.json + avatar.png) with fabric-secrets store settings-put

Accepting an avatar (ADR-056 rule 1/7): build a tree dir holding `profile.json`
(schema `identities/schemas/persona-profile.schema.json`, sha256 of the image,
`avatar.candidate`, `accepted` date) and `avatar.png`; run
`fabric-secrets store settings-put --from DIR` (one signed commit, pushed,
files land under `settings/`). Own agent id: `fabric-secrets store id`.
Candidates: `/usr/local/share/agent-fabric/avatars/<id>/<n>.png`.

**Why:** the command reads the schema from the *working copy the session runs
in* (fabric root), not from cwd. A working copy behind origin/main lacks the
schema and the command refuses with "cannot be checked"; running it from
another checkout does not help.

**How to apply:** fast-forward the session's working copy to origin/main first
(`git merge --ff-only origin/main`), then run. Also: composing a message with
`gzcoord-compose` and filling it by a script that raises sends an empty body
if the script's `&&`/`;` chain still reaches `gzcoord-send` — check the file
before sending (j44 made the sender refuse it).

*Anchors: `tools/fabric/secretstore/settings.py::settings_put`*

*Observed 2026-10-14 (python-dev)*
