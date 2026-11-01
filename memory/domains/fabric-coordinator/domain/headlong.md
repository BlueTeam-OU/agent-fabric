---
role: "fabric-coordinator"
class: domain
topic: headlong
description: "laude-institute/headlong: a Bash agent microharness (~11K lines, Apache-2.0, 1.3k stars), always thinking, one shared mind for many people, shellm RLM; not adopted; borrow a fleet panic stop, tiered trajectory compaction, ancestry for…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5602ddeeeddb3996
---

## laude-institute/headlong: a Bash agent microharness (~11K lines, Apache-2.0, 1.3k stars), always thinking, one shared mind for many people, shellm RLM; not adopted; borrow a fleet panic stop, tiered trajectory compaction, ancestry for writing subagents, scrubbed bug bundles

https://github.com/laude-institute/headlong (read 2026-10-27 through moli; 890 commits, 1.3k stars, Apache-2.0, alpha research software). It is an "agent microharness": a whole harness in about 11K lines of Bash (capped at 11.5K by cloc), built on Ken Thompson's small-tools philosophy.

- **Persistent agency.** The agent never sleeps and keeps generating thoughts in a self-guided loop (`thinkers`). A human message is not a session: it lands in the single thought stream as an observation, and the agent decides whether and when to answer. Agents get a name and a personality and set their own interests.
- **One mind, many people.** Slack, Telegram and a chat app all feed one timeline. There are no per-user sessions and no walls between people ("assume anything you tell the agent is shared").
- **shellm** is a Bash recursive language model: the model thinks by writing shell commands, running them and reading the output. Bash is its only tool, with `curl` and `jq` for HTTP and JSON.
- **Tools.** `llm` is a multi-provider CLI covering Anthropic, OpenAI, Gemini, OpenRouter and local OpenAI-compatible servers. The others: `traj`, `context`, `mem`, `skills` (SKILL.md), `recap`, `glob`, `view`, `put` and `sub` instead of raw coreutils, `shellm-docker` behind a host-side policy broker, `pr-committee` (multi-model PR review), `headlong-killall` (a panic button that stops every Headlong process) and `<name> bugreport` (logs plus trajectory with keys scrubbed).
- **The trajectory is a DAG of append-only jsonl files** with fork and merge. Context is a projection of it, and nothing is compacted in place. **Tiered compaction** keeps the whole trajectory in context at exponentially decaying resolution: recent entries verbatim, older ones summarised, the tiers serving as an index back to raw entries.
- **Subagents see their ancestors' trajectories:** why they were created and what the parent already tried.
- **Self-improvement by fork, test, merge.** The agent forks the codebase, changes it and runs; good changes are merged and bad forks discarded. Laude has pulled more than 50 of its own agent's commits into main.
- **Containment.** Docker by default, with a host install behind an explicit yes. It asks for a spend-capped key and warns not to give the agent secrets.

**For the fabric:** not adopted.
- A Bash core goes against ADR-040.
- An always-thinking single mind is the opposite of the fabric's job-driven sessions (ADR-037).
- One shared timeline with no walls contradicts login-as-identity and per-agent secrets (ADR-038). See [[trust-philosophy-uniform]].

**Borrow:**
1. **A fleet panic stop.** One command that stops every session, the deck and the control agents ([[fleet-shutdown-procedure]] says no such command exists today).
2. **Tiered, exponentially decaying context compaction** over the jobs, journal and memory, with tiers that index back to raw entries, for session recall.
3. **Writing subagents briefed with their ancestry:** the job, what was already tried, and the failing attempts. Review stays blind (ADR-020).
4. **A `bugreport` bundle** of logs and the session trajectory with secrets scrubbed, for incidents like j417's.
5. **The append-only trajectory DAG with fork and merge** as a model for job history.

*References: fleet-shutdown-procedure, trust-philosophy-uniform*

*Observed 2026-10-27 (fabric-coordinator)*
