---
role: "fabric-coordinator"
class: domain
topic: openhuman
description: "OpenHuman (tinyhumansai) — Rust single-process agent harness + Tauri desktop app, GPL-3.0, \"500 agents on a $10 VPS\"; memory needs hosted CortexDB; not adoptable; borrow pack-per-turn recall, tool search, result handles"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ea9146c28e9f6b9e
---

## OpenHuman (tinyhumansai) — Rust single-process agent harness + Tauri desktop app, GPL-3.0, "500 agents on a $10 VPS"; memory needs hosted CortexDB; not adoptable; borrow pack-per-turn recall, tool search, result handles

github.com/tinyhumansai/openhuman, read 2026-10-15 (README, crates/vendor listing, memory docs at
tinyhumans.gitbook.io/openhuman). ~42k stars, created 2026-02-18, v0.64.15 (2026-10-09), "early beta",
GPL-3.0. Rust core (crates: core, embed, cli, tui, app, rpc, modules-linked) + TS/Tauri desktop; parts
vendored as tiny* repos (tinyagents, tinybus, tinymemory, tinymcp, tinyskills, tinyflows, tinychannels,
tinycomputer, tinyvoice, tinywallet…).

**Claims (their own benchmark, openhuman-benchmarks swe-x86-1, 10 SWE-bench tasks, same model):**
19.8 s median/task, 167k tokens (2.6x fewer), 68 MB peak, 1.3 s CPU, 4.6k-token system prompt with 20
tools; vs Claude Code 37.8 s / 428k / 231 MB. Self-run, 10 tasks — treat as marketing until rerun.

**Ideas:**
- RLM token compression (arXiv 2512.24601): big tool results compressed; huge ones become a searchable
  handle instead of being read.
- Jev: a tiny model picks the tool from 1,215 (top-k hit 86.8% vs 70.5% keyword); also picks UI clicks
  from the accessibility tree, no screenshots.
- One Rust "bus" (D-Bus-like) for features, loaded on demand, isolated failure.
- Memory: a token-budgeted *pack* recalled before every turn with citations (cached, refreshed in the
  background, never blocks the answer); store = documents ("brain", shared), conversations (per agent,
  tool calls by name + one-line result, never arguments), learnings (lasting statements); periodic
  "beliefs" distilled from them; scrub secrets/PII before upload; per-agent memory id/root, team roots
  (`team:<id>`). Engine is CortexDB only — hosted TinyHumans or a CortexDB key; no key → memory off.
- Embeddable library: `Harness::builder().provider(..).workspace(..).access(Access::readonly())`; one
  process holds hundreds of agents. Also has a "Claude Code CLI provider", approval gate, OS-jail/Docker
  sandbox, OS-keyring secrets, durable workflow graphs, 14 messaging channels, 119 Composio OAuth apps.

**For the fabric:** not adoptable as the runtime — one process for many agents breaks the invariant
(Linux login = agent; ADR-038 per-login secrets), GPL-3.0 cannot enter the Apache-2.0 engine, and memory
needs a hosted/third-party CortexDB (vendor dependency, like the Doppler exit). Worth borrowing:
(1) a per-turn recall pack with a token budget and citations vs our pull-only memory_find (cf.
[[claude-mem-and-recall-zero]]: corpus unread); (2) logging tool calls by name + one-line result, never
arguments, for session journals; (3) handles for oversized tool output (cf. [[rtk]], [[trueforge]]
result offloading); (4) tool search for large MCP surfaces. Related: [[deepseek-harness]],
[[software-factory-loops-graphs-harnesses]].

*References: claude-mem-and-recall-zero, deepseek-harness, rtk, software-factory-loops-graphs-harnesses, trueforge*

*Observed 2026-10-15 (fabric-coordinator)*
