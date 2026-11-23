---
role: "rust-services-dev"
class: domain
topic: "stub-must-refuse-what-the-server-refuses"
description: Measuring whether a model calls an MCP tool through a stub — Claude Code passes arguments the schema forbids, so a lenient stub counts calls the real server refuses
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 6e1ee4de02ba316a
---

## Measuring whether a model calls an MCP tool through a stub — Claude Code passes arguments the schema forbids, so a lenient stub counts calls the real server refuses

Claude Code 2.1.311 does not hold a `tools/call` to the server's advertised
`inputSchema`: with `additionalProperties: false` and `content` required,
Sonnet 5.5 called the bridge's `reply` with `text` or `message` in place of
`content` in 4 of the 10 lenient-stub runs kept apart in
`runs/s32-lenient-stub/`, and in 3 of the 10 counted plugin-question text
and idle runs under the strict stub (idle-2, idle-5, text-1; 0 of 10 in
the tool cells) -- SPIKE-001 S32 (b), README fact 95 -- and the host sent
the call as made. A stub that answers any arguments counts
those as successes, though the bridge's `deny_unknown_fields` input refuses
them with -32602. Given that refusal, the model called again correctly, 3 of 3.

**Why:** a fake proves only what it implements; the lenient stub
over-counted "replies" that would have reached no peer.

**How to apply:** a stub standing in for a server in a model-behaviour
measurement refuses exactly what the server refuses (schema, unknown and
missing fields, its error code and message), and the measure counts only
accepted calls. Read the server's surface (instructions, tools) from its
source at run time, as `s32_reply.py`'s `bridge_surface` does, so it
cannot go stale. See [[print-session-closed-stdin-ends-channel]].

*References: print-session-closed-stdin-ends-channel*

*Observed 2026-11-10 (rust-services-dev)*
