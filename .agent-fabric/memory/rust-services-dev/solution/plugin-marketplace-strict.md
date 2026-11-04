---
role: "rust-services-dev"
class: solution
topic: "plugin-marketplace-strict"
description: "Claude Code 2.1.286 `plugin validate --strict` fails a marketplace.json without metadata.description"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 23ec65435fbe92a0
---

## Claude Code 2.1.286 `plugin validate --strict` fails a marketplace.json without metadata.description

Measured 2026-10-20 (InterWeave j36, branch develop-qzapp/rust-services-dev-02/feat/j36-claude-plugin-channels-measure,
commit 7d506e30) on Claude Code 2.1.286 with a scratch CLAUDE_CONFIG_DIR:
- packaging/claude-plugin/.claude-plugin/marketplace.json passes `claude plugin validate --strict` only once
  `metadata.description` is present.
- `plugin marketplace add` followed by `install interweave@interweave` succeeds, and the plugin is enabled at
  user scope.
- The installed bin/claude-channel keeps mode 0755.
- The bridge answers initialize with experimental `claude/channel` and no daemon running.
The session runs (--channels and the development flag) were not measured: see [[classifier-session-driver]].

*References: classifier-session-driver*

*Observed 2026-10-21 (rust-services-dev)*
