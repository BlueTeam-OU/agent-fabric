---
role: "fabric-coordinator"
class: workflow
topic: "safeguard-refusal-stalls-agent"
description: "A model safeguard refusal (API Error ... safeguards flagged) stalls an agent's session until a person acts; restart --resume brings the flagged turn back; recover with /clear + a resume nudge"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7c0f5585a688235a
---

## A model safeguard refusal (API Error ... safeguards flagged) stalls an agent's session until a person acts; restart --resume brings the flagged turn back; recover with /clear + a resume nudge

2026-10-18, language-culture-ge: Claude Code showed "API Error: Opus 5.5's safeguards flagged this message …
[reasoning_extraction]" and waited for a person (edit the message, or /model). Nothing in the fleet noticed.

- `fabric-ctl <login> restart` relaunches with --resume, so the conversation, flagged turn included, comes back and
  can be refused again. The clean unstick is `/clear` in the pane (system prompt and role stay), then a nudge to run
  `fabric-jobs list` and continue, typed with `agent-fabric-fleetdeck pane send-text`/`send-keys` ([[type-into-ssh-pane]]).
- Asked rust-ui-dev-02 (REQUEST 01a150b2-1e37) for the deck to do this once per pane per hour and report; asked
  language-culture-ge which job tripped it (likely translating prompt texts, harness.md among them).

**Why:** an agent stalled on a refusal holds its whole queue.
**How to apply:** a stuck agent: read its pane first; on this error, /clear + nudge, never restart --resume.

*References: type-into-ssh-pane*

*Anchors: `tools/fabric/control/restart.py::--resume`*

*Observed 2026-10-18 (fabric-coordinator)*
