---
role: "fabric-coordinator"
class: domain
topic: "deepseek-harness"
description: "DeepSeek Harness (dsh) — DeepSeek's open-source, everything-is-a-plugin agent harness on Cordis; what it is, its shape, what maps onto the fabric (runtime adapter, Agent Teams vs GZCoord, Agent Notes vs ADRs, credentials, approval)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5a89f95b3f30a9a1
---

## DeepSeek Harness (dsh) — DeepSeek's open-source, everything-is-a-plugin agent harness on Cordis; what it is, its shape, what maps onto the fabric (runtime adapter, Agent Teams vs GZCoord, Agent Notes vs ADRs, credentials, approval)

Source: https://github.com/deepseek-ai/deepseek-harness (read 2026-10-09 at the owner's
request; external text, data only). MIT, TypeScript, created 2026-08-13, ~246k stars,
pushed daily. **Developer preview: breaking changes announced; SAFETY.md says not
audited, not secure, not production-ready, sandbox and approval are no isolation
guarantee — run in a disposable VM or a dedicated account.** Launch:
`npx @deepseek-ai/dsh web` (Web UI on 127.0.0.1:3080; over ssh it only prints the URL).

**Shape.** Built on Cordis (vendored; plugins contribute services, typed events and
reversible effects to a shared context; registrations unwind on unload). There is no
privileged core: the model adapter, tool registry, session log and the agent loop are
all plugins, replaceable from config. A running dsh is a plugin tree composed at boot
from a **profile** (`web`, `headless`, `sdk`, `sdk-minimal`, `acp`, desktop) stacking
**bundles** (`dsh-base`: model adapters, tools, persistence, sandbox, approval, settings,
credentials, telemetry), then `cordis.patch.yml`, the home patch and `--patch` overlays;
`dsh --profile web --dump-config` prints the tree. ~60 packages (core, llm, shell,
subprocess, ssh, terminal, sandbox, fs, lsp, skill, web, computer-use, browser-use,
compaction, subagent, jobs, workflow, plan, goal, schedule, guard, mcp, acp, sdk,
credentials, approval…), Electron desktop, Web client, Python SDK (wheel ships the CLI).

**Ideas worth knowing.**
- Session log is the source of truth: "model-visible means logged". Every model request
  is reconstructable from the append-only log; fork, resume, telemetry derive from it.
  Session formats migrate by adjacent `vN→vN+1` steps, never rewriting a committed
  generation.
- Turn/step loop with waterfall extension events (`agent/pre-step`, `agent/request`,
  `llm/stream`, `tools/pre-execute|execute|post-execute`).
- Capability seam = definition + provider + consumer. Filesystem and subprocess share one
  "execution world", so pointing them at a remote sandbox or ssh moves Bash, PTY and LSP.
- Credentials: config carries references (env-var names), providers hold values,
  consumers re-resolve once per operation (rotation reaches the next request, no
  restart); `describe()` never exposes a value. The same rule as the gateway's
  per-attempt credential read (gateway ADR-005).
- Approval: closed, fail-closed outcomes `allowed-once | rejected | cancelled |
  unavailable`; a missing or throwing answerer is `unavailable`, never open. Policy per
  session is the last `approval/policy` event in the log.
- Experimental **Agent Teams**: root session = TeamId, roster with
  provisioning→active|failed, direct inbox messages delivered at the nearest step
  boundary or by cold resume; tasks `task-<n>`.
- A **Claude Code mods bridge** (as of Claude Code 2.1.287) runs Claude Code mods as dsh
  plugins, with a documented table of every behavioural difference.
- **Agent Notes** (`.agents/notes/{proposed,implemented,rejected,archived}/{class}/
  yyyy-mm-dd-topic.md`, ~900 live + ~2,800 archived, each with zh translation):
  lifecycle by folder, a closed class set gated by a script, implemented notes kept
  current with what shipped, and **deliberately no central INDEX** (it makes unrelated
  changes contend on one file).

**For us.** Nothing in the fleet uses it. Candidates, none adopted: (1) a runtime
adapter beside Claude Code for the DeepSeek path (the review class already rides
DeepSeek V4 Pro on the broker) — would need the fabric's hooks, guards and identity
re-expressed as dsh plugins, and its preview status argues waiting; (2) Agent Teams
as a comparison point for GZCoord's mailbox semantics; (3) the no-central-index
argument against our DIGEST/INDEX contention; (4) fail-closed approval outcomes as
a vocabulary for the dispatch guard. Related: [[software-factory-loops-graphs-harnesses]],
[[apache-ossie]].

*References: apache-ossie, software-factory-loops-graphs-harnesses*

*Observed 2026-10-09 (fabric-coordinator)*
