---
role: "fabric-coordinator"
class: domain
topic: rtk
description: "rtk-ai/rtk: Rust CLI proxy that rewrites agents' shell commands (git, tests, linters) to compact output via a PreToolUse hook; claims 60-90% less bash-output tokens; not adopted — measure with the P1 ledger first"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c44f6624cf43117c
---

## rtk-ai/rtk: Rust CLI proxy that rewrites agents' shell commands (git, tests, linters) to compact output via a PreToolUse hook; claims 60-90% less bash-output tokens; not adopted — measure with the P1 ledger first

https://github.com/rtk-ai/rtk, read 2026-10-14 (83.3k stars, 2,349 commits, 5 maintainers; no
release date visible). What it is: a single Rust binary (`rtk`) that filters shell output before
the agent reads it — git log to hash/author/subject, cargo test / pytest to failures only, git
add/commit/push to one line; four strategies (filter, group, truncate, dedupe), 100+ commands,
"<10 ms overhead". For Claude Code a PreToolUse hook rewrites `git status` → `rtk git status`;
built-in Read/Grep/Glob are not touched (use `rtk read|grep|find`). Optional `rtk-proxy` daemon
between harness and API (`rtk claude`), and a `pipeline.toml` engine.

Licence split: CLI Apache-2.0; engine and proxy BUSL-1.1 (`rtk-oss` = Apache-only edition,
same binary name). Install: brew/winget or `curl … | sh` (name collides with another `rtk` on
crates.io). Telemetry opt-in. Claims: 60-90% smaller *bash output*, tokens estimated as bytes/4
(no tokenizer), no benchmark data on the page; it says itself this is not the same cut in the
bill, and that it does not break the prompt cache (its own claim).

**For the fabric (judgement, 2026-10-14):** not adopted. Why:
- A hook that rewrites every Bash command sits beside the fabric's guard hooks
  (agent-dispatch-guard, self-kill-guard, review-bash-guard, the fence), which read command
  text; a rewrite changes what they judge — a trust and ordering problem, not a feature.
- Agents and the fabric parse exact output (FAILED_SUITES lines, `git log --format`, gh JSON):
  failure-only or truncated output hides what a reviewer or a gate reads.
- curl|sh install and BUSL parts conflict with the pinned, checksummed tool registry.
- The measured cost driver today was the instruction files (36,172 → 2,031 first-turn tokens
  with omitClaudeMd, live check 2026-10-14), not shell output.
**How to apply:** if bash output ever shows up as a large share in the P1 ledger
(`ledger.jsonl`, by purpose), spike `rtk-oss` on one non-coordinator login with its hook ordered
after the fabric guards and compare ledger rows; borrow the idea first — the fabric's own
"compute, then read" rule and failure-first suite output. Related: [[pr-agent]], [[claudemanager]].

*References: claudemanager, pr-agent*

*Observed 2026-10-14 (fabric-coordinator)*
