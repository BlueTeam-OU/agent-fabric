---
role: "p2p-network-dev"
class: domain
topic: "claude-code-sends-no-channel-capability"
description: "Claude Code's MCP initialize does not declare claude/channel (that is a SERVER capability the bridge advertises), so a bridge cannot detect push-capable hosts from the client's capabilities; the delivery mode must be explicit…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9ef09f16c16c8936
---

## Claude Code's MCP initialize does not declare claude/channel (that is a SERVER capability the bridge advertises), so a bridge cannot detect push-capable hosts from the client's capabilities; the delivery mode must be explicit configuration with no default

The first plan for generalising the bridge to any MCP host (#221,
2026-10-07) was to push to the host when it declared `claude/channel` at
initialize, and to use pull otherwise. Every SPIKE-001 recording of Claude
Code 2.1.285's initialize (for example spikes/spike-001/runs/t4-delivery/stub.jsonl
line 4, and the r1/r2/r4/t5–t7 runs) carries only `{"roots":
{"listChanged": true}, "elicitation": {...}}`. `experimental["claude/channel"]`
is something the SERVER advertises. Keyed on the host's capabilities, the
bridge would have put the one host that works into pull mode.

Ruling (DECISION 01a11820): the mode is `--delivery push|pull`, required,
with no default. A process started without it refuses to start and names
both values. The plugin's .mcp.json passes `--delivery push`. The bridge
advertises `claude/channel` only in push mode and the receive tool only in
pull mode (apps/claude-channel/src/mcp.rs).

**How to apply:** before choosing behaviour from a peer's advertised
capabilities, check a recorded handshake to see which side declares the
capability. When the client cannot say what it supports, make the choice
explicit configuration, and refuse to start without it rather than default
into a mode that breaks the working host. More measured channel facts:
[[claude-code-channel-facts-2-1-285]].

*References: claude-code-channel-facts-2-1-285*

*Observed 2026-10-25 (p2p-network-dev)*
