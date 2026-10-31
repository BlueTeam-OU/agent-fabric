---
role: "fabric-coordinator"
class: workflow
topic: "type-into-ssh-pane"
description: "How to type the owner's words into another agent's session when its deck pane is an ssh link; why language-culture-ge sat idle on 11 queued jobs"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cfbbebbb2b84d54b
---

## How to type the owner's words into another agent's session when its deck pane is an ssh link; why language-culture-ge sat idle on 11 queued jobs

To relay the owner's words into another agent's session (2026-10-16, language-culture-ge):

- `agent-fabric-fleetdeck agent prompt` and `agent send-keys` refuse a pane whose foreground process is the ssh client, with "agent_not_ready".
- `agent-fabric-fleetdeck pane send-text <pane> "<text>"` followed by `pane send-keys <pane> enter` works.
- Find the pane with `agent list` (the account sits in `tokens.account`), and read the result back with `agent read <pane>`.
- `agent read` can return a stale snapshot: on 2026-10-16 18:5x it showed the same screen after three sends. `pane read <pane>` is live, so read back with that.
- Grey text after `❯` is Claude Code's prompt suggestion, not typed text, and Enter does not send it.
- Label the text as the owner's word relayed by fabric-coordinator.
- Second occurrence, 2026-10-16: language-culture-ge again held a written j72 REPLY "waiting for your go-ahead". The fleet rule (a REPLY-EXPECTED request is always answered) was enough authority, so I typed that myself. It recurs, so its charter or brief needs the line.

Why it was idle: language-culture-ge held eleven queued requests (j59-j69), waiting for the owner to confirm them, although a queued REQUEST is already its job. It also read only the first 14 lines of my inbox delivery, so it saw the headers but not the body.

**How to apply:** when an agent idles on a queued list, read its pane first. If it is waiting on the owner, relay the owner's words this way. If the same misreading shows up in a second agent, fix it in the inbox skill or the team prompt.

*Observed 2026-10-16 (fabric-coordinator)*
