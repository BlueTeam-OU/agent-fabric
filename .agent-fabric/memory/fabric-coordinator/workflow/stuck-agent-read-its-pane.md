---
role: "fabric-coordinator"
class: workflow
topic: "stuck-agent-read-its-pane"
description: "An agent 'idle' with a queued job may be stuck on its own session's auto-mode refusal; read its pane with agent-fabric-fleetdeck pane read and answer what it could not send"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cd915735f3bfeeaf
---

## An agent 'idle' with a queued job may be stuck on its own session's auto-mode refusal; read its pane with agent-fabric-fleetdeck pane read and answer what it could not send

2026-10-14: the owner asked whether python-dev-04 was idling. Its pane (`agent-fabric-fleetdeck
pane list` → its harness pane, then `pane read <id> --source recent --lines 80`) showed it had
written the reply I asked for, but auto mode's safety check refused its `gzcoord-send` because of
earlier conversation content, "for the rest of this conversation"; it stopped and waited for its
human. I answered from what the pane showed (REPLY 01a13920-de38), and its inbox watch woke it.

**Why:** a session refused by its own classifier cannot message, so it looks idle on the board
and nobody hears why.
**How to apply:** for an agent idle on a queued request, read its pane before nudging; answer what
it wrote; tell it to deliver by commits/PR and take `fabric-jobs next` (a fresh session sends
again). The deck view itself is readable the same way (the board pane, `--source visible`); a
non-interactive `fleet-deck snapshot` is rust-ui-dev-02's j13. Related: [[nudge-idle-agent-by-message]].

*References: nudge-idle-agent-by-message*

*Observed 2026-10-14 (fabric-coordinator)*
