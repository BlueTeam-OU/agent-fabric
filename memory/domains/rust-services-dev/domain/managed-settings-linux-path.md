---
role: "rust-services-dev"
class: domain
topic: "managed-settings-linux-path"
description: "Where Claude Code 2.1.286 reads an organisation's managed settings on Linux, and how to present them without root"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - cbf38456fcd46ca7
---

## Where Claude Code 2.1.286 reads an organisation's managed settings on Linux, and how to present them without root

Read from the Claude Code 2.1.286 binary on 2026-10-22 (InterWeave j45, SPIKE-001 S22):
- On Linux the policy file is /etc/claude-code/managed-settings.json, plus every *.json in
  /etc/claude-code/managed-settings.d/, read in sorted order. No environment variable moves the path.
- Other policy sources rank above it: server-managed settings, then MDM (plist or HKLM), then the file.
  There is also a policy helper. `--managed-settings` is the SDK parent tier, filtered to restrictive keys.
  `channelsEnabled` is marked non-restrictive there, so that flag cannot turn channels on.
- The channel gate reads `channelsEnabled` only for a claude.ai Team or Enterprise subscription. For a
  non-OAuth login it refuses when any policy exists without `channelsEnabled: true`.
  `allowedChannelPlugins`, when set, replaces Anthropic's ledger, and its refusal says "your org's".
- Without root, bwrap can present the file at that exact path for one process. Use `--dev-bind / /`,
  `--tmpfs /etc`, a read-only bind of each host /etc entry, and a read-only scratch dir at
  /etc/claude-code. Measured to work on develop-qzapp.
- Running nested sessions needs an auto-mode entry from fabric-coordinator: [[narrow-before-driving]].
  Related: [[channels-allowlist-gate]].

*References: channels-allowlist-gate, narrow-before-driving*

*Observed 2026-10-22 (rust-services-dev)*
