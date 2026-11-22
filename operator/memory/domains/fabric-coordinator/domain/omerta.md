---
role: "fabric-coordinator"
class: domain
topic: omerta
description: "shcherbak-ai/omerta: an MIT pre-commit hook and CLI that fails when a value of your own .env files is staged, tracked or in git history (not patterns); not adopted; borrow a value-based check of each account's secrets.env in the commit hook"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bf5320ed3c9c7293
---

## shcherbak-ai/omerta: an MIT pre-commit hook and CLI that fails when a value of your own .env files is staged, tracked or in git history (not patterns); not adopted; borrow a value-based check of each account's secrets.env in the commit hook

https://github.com/shcherbak-ai/omerta (read 2026-10-27 through moli; v0.1.2, 39 commits, 11 stars, MIT, PyPI `omerta`, Python 3.11+). It catches `.env` secrets leaking into git by searching for **your actual values**, not for patterns that look like keys, as gitleaks and TruffleHog do. So it catches secrets of any format: a small provider's key, a bucket name, an organisation ID.

- **Commands.** `omerta check` searches the staged changes, `check --all` every tracked file, `check PATH` a subtree. `history` searches every file version and message reachable from a branch, a tag or HEAD, and reports a value at the commit where it enters a file.
- **Where values come from.** Untracked `.env` and `.env.*` at the repository root, with templates skipped. A tracked env file is a finding in itself. In CI, which has no `.env`, it looks for committed env files instead.
- **How values are searched.** As written, percent-encoded, JSON-escaped and base64-encoded, in text, binary files and file names. Values under 8 characters are skipped (`min-chars`). Non-secret variables go in `ignore` (`.omerta.toml` or `[tool.omerta]`). A rotated key can still be found by keeping the old value in an untracked `.env.old`.
- **Output.** Never prints a value: `path:line: VAR (from .env)`, and a variable name stands in for a value found in a file name. Exit 0 (clean), 1 (found), 2 (error). `--json` gives JSON Lines.
- **Security.** Two dependencies pinned to exact versions, hyperscan among them. git runs by absolute path, never from inside the checked repository, and never gets a value on its command line. Offline.

**For the fabric:** not adopted; its method was borrowed in j424 (2026-10-30) as ADR-012 §5 rule 9, `tools/fabric/guards/secret_values.py`, on PR #433's branch: pre-commit, commit-msg and pre-push, no CI leg (CI holds no values). The history audit of agent-fabric and InterWeave (remotes and tags) found none of the coordinator's 5 values; other accounts' values were not audited.
- Its env-file patterns are relative to the repository root, while an agent's secrets live in `~/.config/agent-fabric/secrets.env` and its pass store (ADR-038).
- hyperscan is a non-stdlib dependency, which goes against ADR-040 for guards.
- Until j424 the "no secret in a commit" rule was only INSTRUCTED (an auto-mode hard_deny line plus CLAUDE.md); rule 9 makes it WIRED at the keyboard. See [[agent-enforcement-audit]] for that WIRED/INSTRUCTED split.

**Borrow:** a stdlib check in `tools/fabric/guards/commit_hooks.py` pre-commit, and in CI on the committed tree, that reads the committing account's own `secrets.env` values (min 8 chars, an ignore list) and refuses a staged diff, file name or commit message containing one, as written, percent-encoded, JSON-escaped or base64. It names the variable, never the value, and never passes a value to git's argv. Also a `history` mode for an audit of public repositories (agent-fabric and InterWeave are public). Related: [[trust-philosophy-uniform]].

*References: agent-enforcement-audit, trust-philosophy-uniform*

*Observed 2026-10-27 (fabric-coordinator)*
