---
role: "fabric-coordinator"
class: workflow
topic: "launcher-help-is-a-launch"
description: "runtime/openrouter/launch --help is a real launch — it rewrites ~/.claude/agents for its provider; read usage from the source, never by running it"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 27d54ffc79996488
---

## runtime/openrouter/launch --help is a real launch — it rewrites ~/.claude/agents for its provider; read usage from the source, never by running it

`runtime/openrouter/launch --help` (2026-10-02) did not print the launcher's usage: it ran a launch on the OpenRouter provider, which reinstalled this account's `~/.claude/agents/*.md` for that provider before handing `--help` to claude. The dispatch guard then refused every review dispatch in the running anthropic session (the reviewer file named the OpenRouter model), and `tests/test_dispatch_guard.py` failed 7 checks because it read that live state.

**Why:** the launcher passes unknown arguments to claude and does its provider setup (agent files) before the exec.

**How to apply:** read the launcher's options from its source or `tools/fabric/launch.py`'s docstring, never by running it; to compare `--print` output use `tests/parity/launch_print.py`, which fakes `ori` and `claude`. If it happens: `runtime/claude-code/install-agent-files.sh --provider "$AGENT_FABRIC_LAUNCH_PROVIDER"` restores this session's files. Related: [[run-suites-as-ci-before-push]].

Update 2026-10-04: a82a9152 (branch develop-qzapp/user/fix/agent-files-provider) makes -h/--help before any `--` skip the agent-file install; until it merges and distributes, the old behaviour stands. Also a169895e: the installer's default provider follows the account's last launch.

*References: run-suites-as-ci-before-push*

*Observed 2026-10-01 (fabric-coordinator)*
