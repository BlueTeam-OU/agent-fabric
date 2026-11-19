---
role: "fabric-coordinator"
class: solution
topic: "dispatch-hook-single-run-2-1-322"
description: "On Claude Code 2.1.322 run_in_background no longer reruns the managed Agent hook on updatedInput; how to count guard runs (strace, a fabric-launch env)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a0d35f8f9bc8013c
---

## On Claude Code 2.1.322 run_in_background no longer reruns the managed Agent hook on updatedInput; how to count guard runs (strace, a fabric-launch env)

On 2.1.286 and 2.1.311 a dispatch with `run_in_background: true` ran the managed Agent `PreToolUse` hook a second
time, on the first run's `updatedInput` (docs/live-checks/2026-11-02-dispatch-hook-reruns-on-updated-input.md);
the dispatch guard accepts its own answer since #458 (j549). On 2.1.322 (2026-11-10, j749,
docs/live-checks/2026-11-10-claude-code-2-1-322-readback.md D1/D2) each dispatch shows one guard run, with or
without the flag, and both run in the background anyway. Keep the acceptance while accounts run mixed builds.

**How to measure it:** the guard rewrites a review call only under a fabric launch, so a `claude -p` child needs
`AGENT_FABRIC_LAUNCH_PROVIDER=anthropic` in its env, or the allow path is never taken. Run the child under
`strace -f -ff -e trace=execve,openat`. A guard run is one `execve` of `hook_entry.py agent-dispatch-guard`; its
child process (argv truncated by strace) opens the snapshot's `dispatch_guard.py` once and
`~/.claude/agents/code-review.md` twice on the allow path. The harness's own single open of code-review.md at
start is in a node thread with no execve.

Also on 2.1.322: `CLAUDE_CODE_SUBAGENT_EFFORT` (2.1.316+) applies only to a subagent whose definition names no
effort (the harness types). ADR-006 rule 6 now refuses it, and the launcher's refusal is python-dev-01's j225
(REQUEST 01a1c63c).

*Anchors: `tools/fabric/guards/dispatch_guard.py::def launch_pins`, `tools/fabric/guards/model_pins.py::CLAUDE_CODE_SUBAGENT_EFFORT`*

*Observed 2026-11-10 (fabric-coordinator)*
