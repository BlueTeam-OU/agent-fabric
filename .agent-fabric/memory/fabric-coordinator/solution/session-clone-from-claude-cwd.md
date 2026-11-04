---
role: "fabric-coordinator"
class: solution
topic: "session-clone-from-claude-cwd"
description: "a Bash-run tool that needs the session's clone — CLAUDE_PROJECT_DIR is not in a Bash call's env; read the claude ancestor's /proc cwd, and neutralise it in tests"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e419afeb0f5e7558
---

## a Bash-run tool that needs the session's clone — CLAUDE_PROJECT_DIR is not in a Bash call's env; read the claude ancestor's /proc cwd, and neutralise it in tests

CLAUDE_PROJECT_DIR reaches hooks and MCP servers but not a Bash call's
environment (checked 2026-10-30: unset in Bash). A tool run from Bash
finds the session's clone as the cwd of its nearest `claude` ancestor
(`review_brief.dispatching_session_pid` + readlink /proc/<pid>/cwd;
`review_brief.session_clone`, j418, commit a7a2b088 on #433).

Trap: tests/run.sh launched from a session also has that ancestor, so a
check keyed on it judges fixture repos differently in a session and in
CI. Give it an override env (here FABRIC_REVIEW_SESSION_CLONE, "" = no
session) and set it in each test module that renders against fixture
repos; the first full run caught test_review_gateway via Codex, which
must be exempt (engine codex reads its clone itself).

*Anchors: `tools/fabric/review_brief.py::def session_clone`, `tools/fabric/review_brief.py::FABRIC_REVIEW_SESSION_CLONE`*

*Observed 2026-10-30 (fabric-coordinator)*
