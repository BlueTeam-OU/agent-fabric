---
role: "python-dev"
class: solution
topic: "j48-blockers-agrees-with-settle-merged"
description: "#279 merged: request blockers clear on any inbound type with non-empty IN-REPLY-TO; arming minimum in agent-fabric is 1 work commit"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c23e56e904560aba
---

## #279 merged: request blockers clear on any inbound type with non-empty IN-REPLY-TO; arming minimum in agent-fabric is 1 work commit

BlueTeam-OU/agent-fabric#279 merged (1 work, 1 fix): `blockers.check_request` drops the `type='REPLY'` filter, so it reads inbound answers as settle.py reads outbound ones; the jobs.py docstring states the owed window and the unreadable-receipt-time rule (owed only for a row that asks this login for a reply).

**Why:** the owner's REQUEST 01a142fd. Known unproven risk: the sender is not compared with the request's addressee; the coordinator said to raise it if a blocker clears on a third party's message. ADR-037 lines 140-141 still said "REPLY" and are the coordinator's to change.

**How to apply:** agent-fabric's arming minimum is 1 work commit (owner, 2026-10-11): `fabric-pr arm N --dry-run --basis "..."` (basis is required even for the dry run), arm yourself once CI incl. platform-smoke is green. Review brief: `fabric-review brief req.yaml` with mode, repository, range, pr, objective, requirements; post with `fabric-pr post-review N --model fable` and the fenced dispatch header.

*Observed 2026-10-16 (python-dev)*
