---
role: "python-dev"
class: workflow
topic: "live-two-account-run-j93"
description: "Rule 13 live dual run on InterWeave 0.2.0 (j93): units already up, skip serve/stop, notice message needs a body, run number is single-use"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 553a267e136ba82f
---

## Rule 13 live dual run on InterWeave 0.2.0 (j93): units already up, skip serve/stop, notice message needs a body, run number is single-use

tests/live_interweave_two_accounts.py (J92_RUN, J92_PEER) on 0.2.0: the
interweave-daemon@gzcoord and interweave-client@gzcoord user units are
already active, so `serve`/`stop` are skipped; `check`, `exchange`,
`portcheck` run against the units. Passed 2026-10-28 (run 1793184500000).

**Why:** a sender refuses a J92_RUN it already sent under, so a failed
exchange needs a new number agreed by both sides. My first "starting
exchange" INFO was refused by gzcoord-send (no CONTEXT/NOTES), the peer never
started, and the run was burnt.

**How to apply:** give an INFO a CONTEXT or NOTES body before relying on it to
start the peer; take the script from the peer's branch with
`git checkout FETCH_HEAD -- <file>` and restore it afterwards (commit nothing).

*Anchors: `tests/live_interweave_two_accounts.py::J92_PEER`*

*Observed 2026-10-28 (python-dev)*
