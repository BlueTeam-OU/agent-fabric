# ADR-043 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-09 — A mod or MCP server that runs code passes the fleet's guards

The owner asked for an analysis of a context-saving MCP server (2026-10-09). It runs code in a dozen languages for the session and returns only the output, and its hooks route the session's shell calls to it. The read of its source found that each run is a child process with the session's environment, files and network, so a shell command run through it reaches none of the fleet's `PreToolUse` guards, which see only the harness's own tools. Rule 5 already made every mod a reviewed proposal; rule 8 says what that review refuses: an execution path that bypasses the guards, and a process boundary presented as isolation. No mod of the fleet runs code today.
