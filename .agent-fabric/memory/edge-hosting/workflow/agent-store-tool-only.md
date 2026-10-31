---
role: "edge-hosting"
class: workflow
topic: "agent-store-tool-only"
description: "My fabric-agent-<id> repository is my secrets store: write it only through fabric-secrets, never a hand clone or push"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e9171a4321559e2e
---

## My fabric-agent-<id> repository is my secrets store: write it only through fabric-secrets, never a hand clone or push

The repository `BlueTeam-OU/fabric-agent-<id>` is the login's encrypted secrets store (agent-fabric ADR-038, ADR-042). It is written only through its own tool (`fabric-secrets store set|rm|settings-put`), which signs every commit and has it verified on pull. Never clone it or push to it by hand, even for non-secret files such as the persona's `settings/profile.json` and `settings/avatar.png`.

**Why:** on 2026-10-13 I pushed an accepted avatar to it by hand (commit 1bd062c) because brand-comms' request said "commit to your own repository"; fabric-coordinator's broadcast 01a135c5 then said hand writes are refused by design and the avatar goes through `fabric-secrets store settings-put --from <dir>`. It did not: the commit was signed by the account's shared git key, which is no writer of the store, so every pull was refused and `fabric-secrets sync` reported REFUSED until fabric-coordinator rolled the store's remote back to the last good commit (with the owner's word). A hand commit to the store breaks the login's secrets for every tool, not only the file it adds.

**How to apply:** when a request asks you to commit to `fabric-agent-<id>`, look for the store's own command first (`fabric-secrets store --help`); if none exists yet, keep the files in the scratchpad and block the job on the tool, not on the owner. Do not read the store's clone (`~/.local/share/agent-fabric/secrets`) with git by hand either, not even its log for a sha: fabric-coordinator's broadcast 01a136de (2026-10-13) says the tool's own output ("settings: N file(s) committed") is the record.

*Observed 2026-10-13 (edge-hosting)*
