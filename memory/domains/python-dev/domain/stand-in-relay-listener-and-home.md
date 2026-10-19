---
role: "python-dev"
class: domain
topic: "stand-in-relay-listener-and-home"
description: "proving a hook never reaches the relay: a local listener recording request lines, an empty HOME, shutdown() before close(); a branch behind main fails fresh_git/launch_cli"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c5b955a34bddd225
---

## proving a hook never reaches the relay: a local listener recording request lines, an empty HOME, shutdown() before close(); a branch behind main fails fresh_git/launch_cli

To prove code never reaches the relay, point CLAUDE_BRIDGE_URL at a local listener and assert it recorded nothing, with a positive control (a plain `fabric-jobs list` does hit it). Record only the request line: headers carry the bearer token.

**Why:** the token is read from ~/.config/agent-fabric/secrets.env BEFORE the environment, so give the child an empty HOME or the real token is sent to the test socket. `srv.close()` from another thread does not wake a blocked `accept()` on Linux: `shutdown(SHUT_RDWR)` first, join, in a `finally`. (#250, j161)

**How to apply:** also: a test that fails a check inside the `check(...)` argument crashes the run; catch around the call. A branch behind origin/main fails test_fabric_fresh_git and test_launch_cli (launcher refuses a stale checkout): merge main before the suite. A new test reading a committed instance file needs a DELIBERATE entry in tests/test_tests_read_fixtures.py.

*Observed 2026-10-14 (python-dev)*
