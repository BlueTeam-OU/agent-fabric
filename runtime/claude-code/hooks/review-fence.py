#!/usr/bin/env python3
"""runtime/claude-code/hooks/review-fence.py — the review class's tool fence as a managed PreToolUse hook
(agent-fabric ADR-043 rule 2, ADR-065 rule 1).

CONTRACT:
  matcher   Bash|Write|Edit|MultiEdit|NotebookEdit (the managed template's; this module does not re-check the tool)
  stdin     the hook payload, one JSON object
  stdout    a deny when the payload's `agent_type` is `code-review`; nothing otherwise
  exit      0 always

ADR-065 rule 1 gives the review class no Bash and no writing tool, and its agent file lists none. The agent file is
the login's own (install-agent-files.sh writes it under ~/.claude/agents/), so a login that edits it hands its
reviewer Bash again. Managed settings are not the login's: this hook, run from the root-owned snapshot, holds the
rule whatever the agent file says, as the subagent clone guard applies itself by the same field.

A payload that is not a JSON object is no harness payload: the hook cannot tell whose call it is, so it asks rather
than allowing a reviewer's call through it.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)        # `python -I` leaves this directory off
sys.dont_write_bytecode = True  # a non-root run never writes beside a root-owned snapshot
import hook_jq  # noqa: E402

EVENT = "PreToolUse"
REVIEW = "code-review"


def main() -> int:
    text = sys.stdin.buffer.read().decode("utf-8", "replace")
    values, ok = hook_jq.run(text, lambda v: [v])
    if not ok or len(values) != 1 or not isinstance(values[0], dict):
        hook_jq.write(hook_jq.decision(EVENT, "ask", "The review-class fence could not read this call's payload. "
                                       "Approve only if this is not the code-review agent.") + "\n")
        return 0
    payload = values[0]
    if payload.get("agent_type") != REVIEW:
        return 0
    tool = payload.get("tool_name")
    tool = tool if isinstance(tool, str) and tool else "this tool"
    hook_jq.write(hook_jq.decision(EVENT, "deny", f"The review class has no Bash and no writing tool (agent-fabric "
                                   f"ADR-065 rule 1), so {tool} is denied to the code-review agent. Read with Read, "
                                   "Glob, Grep and the review server's tools, and report without it.") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
