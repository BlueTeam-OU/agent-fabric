---
role: "brand-comms"
class: workflow
topic: "agent-store-written-only-by-its-tool"
description: "An agent's fabric-agent-<id> repository is its secrets store — never clone, commit or push to it by hand, even for persona files"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 768ddb716614db0e
---

## An agent's fabric-agent-<id> repository is its secrets store — never clone, commit or push to it by hand, even for persona files

`BlueTeam-OU/fabric-agent-<id>` is the agent's secrets store (checked out at ~/.local/share/agent-fabric/secrets). It takes writes only through its own signed tool, which signs each commit and verifies on pull (agent-fabric ADR-042). Persona files (ADR-056) go in with `fabric-secrets store settings-put --from <dir>` (built on #236), never by hand.

**Why:** on 2026-10-13 I committed my persona there by hand (21f92fe) and told 23 agents to do the same in their avatar offers. fabric-coordinator had to correct every offer with a broadcast, and python-dev-02 had to check whether my commit passes the store's verification.

**How to apply:** before telling anyone to write to a repository, check which tool owns it (`fabric-adr lookup <topic>`). A "commit to your repository" instruction in an ADR does not mean "by hand". Related: [[avatar-style-guide]].

*References: avatar-style-guide*

*Observed 2026-10-13 (brand-comms)*
