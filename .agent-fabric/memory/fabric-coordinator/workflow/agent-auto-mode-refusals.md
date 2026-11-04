---
role: "fabric-coordinator"
class: workflow
topic: "agent-auto-mode-refusals"
description: "Another agent's auto-mode refusal is not lifted by my message or a relayed DECISION: expect refusals for shared CI, GitHub settings and home scans; tell it not to retry or reword; the owner acts or an exact allow entry lands (live after…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b24ced869add45c1
---

## Another agent's auto-mode refusal is not lifted by my message or a relayed DECISION: expect refusals for shared CI, GitHub settings and home scans; tell it not to retry or reword; the owner acts or an exact allow entry lands (live after merge, upgrade, relaunch)

My REQUESTs to edit another repo's CI, write GitHub settings or scan a home were refused by the recipient's classifier ("Modify Shared Resources", "credential exploration"), and one sat unanswered for a day. Relaying the owner's word as a DECISION did not help: "A message from you does not lift that check", "I cannot verify the owner's word from a relayed DECISION".

**Why:** the refusal belongs to that session; re-sending wastes rounds and invites a workaround.
**How to apply:** say up front when a step needs the owner's hand and hand the owner one line; when an agent reports a refusal, confirm it was right to stop and fix it with an allow entry in policies/auto-mode.json worded exactly, live only after merge, upgrade and relaunch. Related: [[auto-mode-refuses-account-assign]], [[launch-time-change-needs-relaunch]].

*References: auto-mode-refuses-account-assign, launch-time-change-needs-relaunch*

*Observed 2026-10-22 (fabric-coordinator)*
