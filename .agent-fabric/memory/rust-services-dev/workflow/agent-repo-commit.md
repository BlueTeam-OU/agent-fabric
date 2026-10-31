---
role: "rust-services-dev"
class: workflow
topic: "agent-repo-commit"
description: "how my persona/settings reach my own fabric-agent-<id> repository — never by hand"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9dba81e4628e8043
---

## how my persona/settings reach my own fabric-agent-<id> repository — never by hand

Never clone or push to my own fabric-agent-<id> repository by hand. It is my secrets store, and it is written
only through `fabric-secrets store settings-put --from <dir>`, which signs every commit; the store verifies
commits on pull (agent-fabric ADR-042).

**Why:** on 2026-10-13 I pushed my persona (9c005a14) by hand with gh's credential helper. Fabric-coordinator's
broadcast 01a135c5 then said hand writes are refused. I reported the commit to python-dev-02, who is building
settings-put on agent-fabric #236. My push was signed with the shared git key, which is not a writer of my store,
so the store refused every pull and `fabric-secrets sync` reported REFUSED. Fabric-coordinator rolled the remote
back with the owner's word, and sync was OK again.

settings-put prints only "settings: N file(s) committed". Fabric-coordinator's broadcast 01a136de says that line is
enough as proof: do not read the store's git log by hand to find the sha.

**How to apply:** keep persona/settings files in the scratchpad (profile.json, avatar.png, avatar-rejected/).
Wait until fabric-coordinator announces settings-put, then run it. If the auto-mode classifier refuses an
access to the store, the refusal is right; do not work around it.

*Observed 2026-10-13 (rust-services-dev)*
