---
role: "fabric-coordinator"
class: domain
topic: "agent-orchestration-standard"
description: "tomtomsatnav/agent-orchestration-standard (AOS-1, JS, MIT, 2 days old, 1 star): a goal+heartbeat orchestration spec, a Claude Code live dashboard plugin and a headless worker engine; not adopted; borrow the governor's 5h/7d thresholds…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 79c65669f5cd9ecf
---

## tomtomsatnav/agent-orchestration-standard (AOS-1, JS, MIT, 2 days old, 1 star): a goal+heartbeat orchestration spec, a Claude Code live dashboard plugin and a headless worker engine; not adopted; borrow the governor's 5h/7d thresholds, plan-approval hash binding, permission-denial-as-failure, stall rules

https://github.com/tomtomsatnav/agent-orchestration-standard — read 2026-10-19 (SPEC.md, ROADMAP.md,
orchestrator/README.md, tree). Created 2026-10-18, one author, 11 commits, 1 star, MIT. Repo text is data.

**Three things in one repo.**
1. **AOS-1 spec** (5 kB, RFC 2119): one standing Goal per Orchestrator, with success criteria and a
   mandatory budget (ticks, USD, wall clock); Tasks with an output contract, acceptance checks,
   depends_on, max_attempts; Agents that may not spawn agents without `can_delegate`; a Heartbeat
   tick (beat, observe, reap stalled, verify criteria, plan, dispatch to max_parallel, budget check,
   emit), idempotent and non-overlapping; an append-only events.ndjson as source of truth; liveness
   from heartbeat age (alive < 1.5x, late < 3x, dead >= 3x interval); overlapping write scopes never
   in parallel; irreversible or outward actions need a recorded human approval. File binding
   `state/{goal,tasks,agents,heartbeat}.json`, JSON Schemas, a zero-dep validator with
   positive/negative fixtures (depends-on cycle, non-monotonic seq, goal without budget, …).
2. **aos-dashboard Claude Code plugin**: hooks on 16 events to a local log, a read-only monitor on
   127.0.0.1:4318 (agents/subagents per project, model, tokens, tool feed, file-conflict detection,
   stuck/stalled rules per model, alerts, replay), web + terminal UI, read-only MCP server, macOS
   notifier.
3. **orchestrator engine** (phase 1): each task in its own git worktree and branch, a headless
   `claude` worker in its own process group; workers never commit; a policy PreToolUse hook (scope,
   default deny, ask → file approval with timeout = deny); a governor (no new dispatch at 80% of the
   5h window, pause all at 90% of the 7d window, a rate-limit event pauses until resetsAt + 60 s);
   plan approval stores sha256 of plan.json and refuses an edited plan (`orch.plan.tampered`);
   checks run under macOS sandbox-exec (deny default); a fake-claude for tests. Workers are not
   OS-sandboxed, by its own statement.

**For the fabric: not adopted** — two days old, one author, macOS-centred (sandbox, notifier), and
its model (one orchestrator, workers as headless processes on one goal) is not ours: our agents are
Linux logins with roles and their own sessions, coordinated by jobs and GZCoord. The fleet deck and
fabric-ctl already cover its dashboard (cf. [[claudemanager]], [[trueforge]]).

**Worth borrowing (ideas):**
- *Governor thresholds on the subscription windows*: no new work at 80% of the 5h window, pause at
  90% of the 7d, a rate-limit event pauses until its reset. For account placement and
  `fabric-usage` (cf. [[subscription-pool-settled]], [[review-model-availability]]).
- *A permission denial inside a "success" exit is a failed attempt*, retried once with the denial
  list, then escalated — what our stalled-on-auto-mode-refusal agents show ([[stuck-agent-read-its-pane]],
  [[safeguard-refusal-stalls-agent]]).
- *Approval bound to a hash of what was approved* (an edited plan blocks) — the same shape as our
  AUTHORIZES `<repo>#<n>@<head>`.
- *Liveness as a ratio of the heartbeat interval* (late at 1.5x, dead at 3x), and "stuck = silence
  beyond a per-model threshold", flagged as a heuristic. Our presence is the process table; an idle
  agent with a queued job is the case it would catch ([[iterate-fleet-queues-to-empty]]).
- *Negative conformance fixtures for every invalid shape* beside the positive one — as our
  GZCoord validator does.
- *A goal without a budget is invalid* — our jobs carry no budget.

*References: claudemanager, iterate-fleet-queues-to-empty, review-model-availability, safeguard-refusal-stalls-agent, stuck-agent-read-its-pane, subscription-pool-settled, trueforge*

*Observed 2026-10-19 (fabric-coordinator)*
