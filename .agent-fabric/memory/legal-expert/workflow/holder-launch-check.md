---
role: "legal-expert"
class: workflow
topic: "holder-launch-check"
description: "How to check after a relaunch that holder addenda reached the launch prompt (launch-holder.json, launch-prompt.md)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "legal-expert-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c9af56867cc229ed
---

## How to check after a relaunch that holder addenda reached the launch prompt (launch-holder.json, launch-prompt.md)

After a relaunch, holder addenda (ADR-060) can be checked in the agent state dir (~/.local/state/agent-fabric/agents/<login>/). In launch-holder.json, store_sha and addenda_commit must match fabric-status's "addenda" line, and its charter and brief texts must appear verbatim in launch-prompt.md. Each addendum is placed right after its own shared text: the charter addendum before the shared brief, the brief addendum before the team section. The "against" map holds the translates_digest of the locale charter.md/brief.md the addenda were written against, not the sha of the addenda themselves; don't report a mismatch there as a defect. Checked for j13, 2026-10-17, store b5639b8.

- j17 (REQUEST 01a14d86, 2026-10-18): ADR-060 stage 6 holder.json installed as store f82a566 ({"locale":"ge","timezone":"Asia/Tbilisi","search":{"country":"ge"}}); sync done pre-relaunch; after relaunch report fabric-status addenda + prompt-drift lines, store HEAD, headings language. Result (session ca34309d): addenda line "store f82a566fe919 addenda commit f82a566fe919", store HEAD f82a566, headings in Georgian. fabric-status printed no prompt-drift line at all: tools/fabric/status.py prompt_drift_line returns None when the launched digest matches, so a missing drift line means no drift, not a missing check. Acceptance REPLY 01a14d88 sent.

*Observed 2026-10-18 (legal-expert)*
