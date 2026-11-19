---
role: "python-dev"
class: workflow
topic: "live-two-account-run-on-030-j139"
description: "j139 rule 13 live check on InterWeave 0.3.0: recipe, what passed, what had no command"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 62712db6f625c4a5
---

## j139 rule 13 live check on InterWeave 0.3.0: recipe, what passed, what had no command

Rule 13's live check (tests/live_interweave_two_accounts.py) on 0.3.0 passed on 2026-11-14: check, exchange, portcheck each exit 0 with J92_RUN and J92_PEER set, units already up so serve/stop skipped (as [[live-two-account-run-j93]]). Both builds print `0.3.0+c0bbe40a9bec`, interweave-human included.

**Why:** the pin covers only transportctl and transport-daemon; interweave-human's --version is a separate command to run and report.
**How to apply:** the share dir a host scratch path does not exist before the first account's exchange creates it. The control link's own check (ADR-029 rule 18) had no command at hand: say "not run" rather than guess. A run with no commit needs no PR; close with `fabric-jobs done --no-artifact`, and `switch` still wants a memory change and answered replies.

*References: live-two-account-run-j93*

*Anchors: `tests/live_interweave_two_accounts.py::phase_exchange`*

*Observed 2026-11-14 (python-dev)*
