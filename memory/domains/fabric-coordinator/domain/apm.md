---
role: "fabric-coordinator"
class: domain
topic: apm
description: "microsoft/apm, Agent Package Manager (Python, MIT, v0.34.0 2026-10-19) — not adopted; borrow lockfile deployed-file hashes, rebuild-in-scratch drift audit, tighten-only policy merge, text vs executable trust gate"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - eba3c6ed1a88e40e
---

## microsoft/apm, Agent Package Manager (Python, MIT, v0.34.0 2026-10-19) — not adopted; borrow lockfile deployed-file hashes, rebuild-in-scratch drift audit, tighten-only policy merge, text vs executable trust gate

microsoft/apm (read 2026-10-20, v0.34.0): `apm.yml` + `apm.lock.yaml` declare and pin an agent's
context (skills, agents, instructions, prompts, hooks, plugins, MCP servers) from any git host,
transitive, deployed into each detected harness (Claude Code, Copilot, Codex, Cursor, Gemini, ...).
No telemetry; no package signing; no runtime sandbox (docs say so).

Not adopted: it writes per-project files and user-scope MCP config into `~/.claude.json`, the
same file `tools/fabric/workspace_trust.py` and the launcher manage, and per-repo manifests
conflict with the fabric's per-login, role-bound distribution (bootstrap + upgrade).

Worth borrowing:
- lockfile records sha256 of every deployed file; `apm audit --ci` rebuilds the install in scratch
  and diffs it against the tree (drift = hand edits, unrecorded files) — a model for checking what
  bootstrap rendered into each account.
- policy inheritance enterprise→org→repo is tighten-only (allow intersect, deny union,
  enforcement max, max-depth 5, cross-host extends refused).
- executable trust gate: text primitives never gated, hooks/bin/MCP/LSP from dependencies need approval.
- hidden-Unicode scan on every install; the fabric scans addenda and messages, not every skill.
- the governance guide has an honest "bypass contract" and "known gaps" section.

Owner 2026-10-20: the drift check is job j304, the hidden-Unicode lint j305; APM's code may be taken and adapted (MIT, keep
attribution), within ADR-040.

Related: [[agent-enforcement-audit]], [[trueforge]]

*References: agent-enforcement-audit, trueforge*

*Observed 2026-10-20 (fabric-coordinator)*
