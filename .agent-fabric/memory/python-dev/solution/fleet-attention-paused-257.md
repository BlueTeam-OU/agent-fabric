---
role: "python-dev"
class: solution
topic: "fleet-attention-paused-257"
description: "fleet.py attention data carries paused beside blocked/pending (#257); unreadable-receipt owed row names its subject"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9e22fd8353ce901e
---

## fleet.py attention data carries paused beside blocked/pending (#257); unreadable-receipt owed row names its subject

#257 (2026-10-14): attention data = {level, reason, since, blocked, pending, paused, ...}. Paused is open work set aside by choice: counted apart, never in `blocked`, never level waiting. The Fleet Deck parser's tolerance of an added key is unverified (precedent: context_pct added the same way).

**Why / how to apply:** a new job state must be added to attention_data's counts and to tests/test_fleet_attention.py's exact-dict assertions (they pin every key). Test for owed rows with a broken receipt time: `broken_row(None, "not a time")` keeps the journaled metadata; the request must be REPLY-EXPECTED yes or the row is skipped before the time matters.

*Anchors: `tools/fabric/fleet.py::attention_data`, `tools/fabric/jobsparts/settle.py::owed_replies`*

*Observed 2026-10-14 (python-dev)*
