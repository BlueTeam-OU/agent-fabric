---
role: "rust-services-dev"
class: domain
topic: "mcp-refused-start"
description: Claude Code does not restart a stdio MCP server that exited; a start that cannot work serves a refusing server instead of exiting
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 94d909bb23f1f9cd
---

## Claude Code does not restart a stdio MCP server that exited; a start that cannot work serves a refusing server instead of exiting

Claude Code 2.1.286 starts a plugin's stdio MCP server once per session and never restarts it.
A server that exits at start, for example on a usage error, an unset XDG_RUNTIME_DIR or a bad
profile, shows the user only "Failed to connect", and nothing says why. This was measured without a
session (InterWeave SPIKE-001 S21): the same bad start was "Failed to connect" before the change
and "Connected" after it.

So a start whose configuration cannot work is *served*, not exited. The server answers `initialize`
and declares none of the capabilities that would make it look working (no `claude/channel`). It
holds no resource such as a lease. It reports a refusal with a machine-readable class from
`status`, and returns it as the error from every other tool. Same principle as "a peer away is a
state, not an exit". The decision record is InterWeave architecture/plugin/LIFECYCLE.md step 1
(A 2026-10-22) and TOOL-SURFACE.md `refused`. It is a field lesson for any MCP server I build that
runs under a host which does not supervise it.

*Observed 2026-10-22 (rust-services-dev)*
