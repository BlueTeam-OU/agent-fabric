---
role: "brand-comms"
class: workflow
topic: "agent-fabric-docs-not-brand-comms-writable"
description: "brand-comms cannot commit to agent-fabric, not even docs/ on a for/ branch; deliver copy as text to the coordinator"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7b9d62644b2ada66
---

## brand-comms cannot commit to agent-fabric, not even docs/ on a for/ branch; deliver copy as text to the coordinator

brand-comms cannot commit anything to agent-fabric, `docs/` included, even on a `<host>/<login>/for/<caller>/<what>` branch. The for/ exception admits only the roles listed under `contributors` in `policies/authority.json` (python-dev, devex-tooling, legal-expert as of 2026-11-11), and the pre-commit hook refused docs/moli.md (job j56, REQUEST 01a1cb9f).

**Why:** a request from the fabric-coordinator session (develop-qzapp/user) asked for a for/user/ branch anyway; the request assumed a carve-out the policy does not grant.

**How to apply:** when agent-fabric copy is requested, tell the requester at once that no branch is possible. Then send the final text whole in the REPLY, between delimiter lines, after the native read; the coordinator commits it. A language-culture read works the same way, on quoted text rather than a commit. Related: [[finding-in-one-language-check-the-other]].

*References: finding-in-one-language-check-the-other*

*Anchors: `policies/authority.json::contributors`*

*Observed 2026-11-11 (brand-comms)*
