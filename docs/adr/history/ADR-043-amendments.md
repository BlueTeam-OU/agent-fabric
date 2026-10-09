# ADR-043 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-09 — A mod or MCP server that runs code passes the fleet's guards

The owner asked for an analysis of a context-saving MCP server (2026-10-09). It runs code in a dozen languages for the session and returns only the output, and its hooks route the session's shell calls to it. The read of its source found that each run is a child process with the session's environment, files and network, so a shell command run through it reaches none of the fleet's `PreToolUse` guards, which see only the harness's own tools. Rule 5 already made every mod a reviewed proposal; rule 8 says what that review refuses: an execution path that bypasses the guards, and a process boundary presented as isolation. No mod of the fleet runs code today.

### Amendment 2026-10-09 — Rule 8 names its gate: the managed MCP allowlist

The blind review of the merged rule 8 (#130's last commits) found that it refused a code-running MCP server "at review" while no rule sent an MCP server to review: rule 5 covers mods, and a login's or a project's own MCP configuration reaches a session unreviewed. gzapp's `.mcp.json` already starts `dart mcp-server`, a Flutter toolkit script and `npx -y @playwright/mcp@latest`, unpinned. Claude Code 2.1.285, the fleet's pin, has managed `allowManagedMcpServersOnly`, `allowedMcpServers` and `deniedMcpServers` (read from the installed build), so the gate is rule 1's file. The review also found the reason too broad: an unmatched `PreToolUse` hook does see an MCP call; what an MCP call escapes are the guards matched to Bash, and what no hook sees is the server's own processes. Both are now said.
