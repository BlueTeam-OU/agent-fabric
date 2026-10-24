---
role: "rust-services-dev"
class: domain
topic: "s19-driver-shape"
description: "Driving a nested claude TUI through a pty: match menu text with spaces squeezed out, and redact ~/ paths"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 181072ceed03a4ae
---

## Driving a nested claude TUI through a pty: match menu text with spaces squeezed out, and redact ~/ paths

From spikes/spike-001/s19_channels.py (InterWeave #355, 2026-10-22), on Claude Code 2.1.286:
- The TUI positions text with cursor moves, so "1. I am using this for local development" reaches the pty as
  "1.Iamusingthisforlocaldevelopment". Squeeze the whitespace out of both the label and the screen before matching.
  An unsqueezed regex found no option and the run never accepted the warning.
- The banner prints the working directory in its "~/" form, so redaction must also replace the home-relative form
  of each scratch path.
- The driver ran under an exact auto-mode allow rule (agent-fabric allow/4, #353). Ask for such a rule before
  drafting a driver that launches sessions with the dev flag ([[classifier-session-driver]]).

*References: classifier-session-driver*

*Observed 2026-10-22 (rust-services-dev)*
