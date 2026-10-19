---
role: "edge-hosting"
class: rationale
description: "Where a site's deploy/upload tooling goes — the site's own repository, generic core; never agent-fabric"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 89cec6543cebcb62
---

## Where a site's deploy/upload tooling goes — the site's own repository, generic core; never agent-fabric

The owner's decision (relayed by fabric-coordinator, 2026-10-11, withdrawing the agent-fabric contributor entry): a site's deploy tooling lives in that site's repository, not in agent-fabric. agent-fabric holds what the agents are and how they work; deploying a site is a project's own work.

**Why:** the uploader was not generic enough to belong to the control plane. Built in blueteam.ee instead, with its core kept free of the site's names (one core, one transport per protocol, a target file per site, the pinned host key, tests with their own sshd) and its procedure as a skill in the site repository's `.claude/skills/`.

**How to apply:** when edge tooling (an uploader, a checker) looks reusable, do not propose it to agent-fabric. Keep it in the project repository with a site-neutral core. If a second site needs it, it moves to its own small tool repository, still not agent-fabric. No ADR records this yet. Related: [[publish-needs-owner-word-in-session]].

*References: publish-needs-owner-word-in-session*

*Observed 2026-10-17 (edge-hosting)*
