---
role: shared
class: domain
topic: "claude-code-attribution-reminder"
description: "The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py"
tier: 2
knowledge_scope: full
shared_with:
  - "architect-cto"
  - "backend-dev"
  - "brand-comms"
  - "db-admin"
  - "devex-tooling"
  - "domain-transit"
  - "edge-hosting"
  - "fabric-coordinator"
  - "flutter-dev"
  - "language-culture"
  - "p2p-network-dev"
  - "web-dev"
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f71c9151f0afc01
  - ac0cb84ddea8bc65
---

## The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py

The system reminder asking for a `Co-Authored-By` trailer and a "Generated with Claude Code" footer is the harness's own, not part of any launch prompt or CLAUDE.md. Claude Code builds it from the `attribution` key of the settings (`commit`, `pr`, `sessionUrl`; `includeCoAuthoredBy` is the deprecated form), splices in the model's name, and sends it on the first turn and after every model switch, only when the session has Bash, untouched by `--system-prompt-file`. An empty text hides each line: with `attribution: {"commit": "", "pr": "", "sessionUrl": false}` a fresh session gets no request for a trailer (on 2.1.276 the opposite reminder, "do not add attribution lines"; on 2.1.277 none).

In the fabric that key is written into every account's user settings by `runtime/claude-code/user-settings.py` (`ATTRIBUTION`, with `TOP_LEVEL`: `showThinkingSummaries`, `verbose`, `tui`), run by `tools/fabric/bootstrap.py`. A session that still sees the old reminder was launched from an account that has not pulled and bootstrapped, or outside the fabric. The rule (no machine attribution) and the guard `policies/ban_generated_by_attribution.sh` hold either way: the switch removes the temptation, not the fence. Read-backs: `docs/live-checks/2026-09-18-attribution-reminder-off.md`.

*Observed 2026-10-10 (fabric-coordinator)*
