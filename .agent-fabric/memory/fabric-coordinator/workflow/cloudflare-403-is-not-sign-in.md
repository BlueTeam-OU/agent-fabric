---
role: "fabric-coordinator"
class: workflow
topic: "cloudflare-403-is-not-sign-in"
description: "\"Please run /login · API Error 403 Attention Required | Cloudflare\" is an edge block, fleet-wide and transient, never the account's sign-in"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4d9871f4573ec9ab
---

## "Please run /login · API Error 403 Attention Required | Cloudflare" is an edge block, fleet-wide and transient, never the account's sign-in

"Please run /login · API Error: 403 Attention Required! | Cloudflare" in a pane is Cloudflare refusing the request at
the api.anthropic.com edge, before authentication. Claude Code prints the /login hint for any 403; /login changes nothing.

Seen 2026-11-13 09:47–09:50 UTC on develop-qzapp: python-dev-02, python-dev-03, p2p-network-dev-01, web-dev-02
(Sonnet and Opus alike), intermittent, some turns between the failures succeeding; the owner's coordinator launch hit it too.
By 09:53 all three account tokens answered (`fabric-accounts observe`), and at 09:55 a headless `claude -p` on the
fabric's own setup-token replied.

**Why:** one egress IP for ~30 sessions; the block is by time window, not by token, account or model.

**How to apply:** do not re-login or move accounts. (1) scan every pane for the string (fleetdeck `pane read` is plain
text, not JSON); (2) `fabric-accounts observe` (dry) and one `claude -p` with `~/.config/agent-fabric/secrets.env`
sourced, token never printed; (3) when both answer, the block is over: a hit session only needs a new prompt. Auto mode
refuses my `pane send-text` nudge (Unsanctioned Communication), so name the stalled panes to the owner.
Related: [[stuck-agent-read-its-pane]], [[safeguard-refusal-stalls-agent]].

*References: safeguard-refusal-stalls-agent, stuck-agent-read-its-pane*

*Anchors: `tools/fabric/control/account_observe.py::fabric-accounts observe`*

*Observed 2026-11-13 (fabric-coordinator)*
