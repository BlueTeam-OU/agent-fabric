---
role: "fabric-coordinator"
class: workflow
topic: "launcher-help-is-a-launch"
description: "launch --help installs no agent files; it still passes through to claude, so read usage from source"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 27d54ffc79996488
  - 974d92ea06ea6406
---

## launch --help installs no agent files; it still passes through to claude, so read usage from source

`launch --help` or `-h` before any `--` no longer rewrites `~/.claude/agents` (tools/fabric/launch.py header); the installer's default provider follows the account's last launch. Before that fix, `runtime/openrouter/launch --help` reinstalled this account's agent files for its provider and the dispatch guard then refused every review in the running session.

It still passes `--help` through to claude, so reading options from `tools/fabric/launch.py`'s docstring remains sound; to compare `--print` output use `tests/parity/launch_print.py`, which fakes `ori` and `claude`. If a session's agent files were rewritten: `runtime/claude-code/install-agent-files.sh --provider "$AGENT_FABRIC_LAUNCH_PROVIDER"` restores them. Related: [[run-suites-as-ci-before-push]].

*References: run-suites-as-ci-before-push*

*Observed 2026-10-10 (fabric-coordinator)*
