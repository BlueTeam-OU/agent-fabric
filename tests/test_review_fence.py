#!/usr/bin/env python3
"""runtime/claude-code/hooks/review-fence.py, the review class's tool fence as a managed PreToolUse hook (agent-fabric
ADR-043 rule 2, ADR-065 rule 1): the code-review agent is denied Bash and every writing tool; any other agent type
and the main session pass in silence; a payload that is not one JSON object asks. Run as the managed entry runs it,
`python -I -S <path>`, so a module it needs beside it but cannot import under -I fails here.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FENCE = os.path.join(ROOT, "runtime", "claude-code", "hooks", "review-fence.py")


def run(payload) -> subprocess.CompletedProcess:
    data = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
    data = data.encode() if isinstance(data, str) else data
    return subprocess.run([sys.executable, "-I", "-S", FENCE], input=data, capture_output=True, timeout=30,
                          env={"PATH": "/usr/bin:/bin"})


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    def decision(r):
        try:
            return json.loads(r.stdout)["hookSpecificOutput"]
        except (ValueError, KeyError, TypeError):
            return {}

    print("review-fence")
    for tool, tool_input in (("Bash", {"command": "ls"}), ("Write", {"file_path": "/tmp/x", "content": "x"}),
                             ("Edit", {"file_path": "/tmp/x"}), ("MultiEdit", {"file_path": "/tmp/x"}),
                             ("NotebookEdit", {"notebook_path": "/tmp/x.ipynb"})):
        r = run({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                 "agent_id": "a1", "agent_type": "code-review", "session_id": "s"})
        d = decision(r)
        check(f"code-review on {tool}: denied, naming the tool and ADR-065 rule 1",
              r.returncode == 0 and d.get("permissionDecision") == "deny" and d.get("hookEventName") == "PreToolUse"
              and tool in d.get("permissionDecisionReason", "") and "ADR-065 rule 1" in d["permissionDecisionReason"],
              (r.returncode, r.stdout, r.stderr))
    for agent_type in ("code-medium", "code-high", "Explore", "general-purpose", "code-reviewer", "Code-Review"):
        r = run({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"},
                 "agent_id": "a1", "agent_type": agent_type})
        check(f"agent type {agent_type!r}: passes in silence", (r.returncode, r.stdout) == (0, b""), r.stdout)
    r = run({"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": "/tmp/x"},
             "session_id": "s"})
    check("the main session (no agent_type): passes in silence", (r.returncode, r.stdout) == (0, b""), r.stdout)
    r = run({"hook_event_name": "PreToolUse", "tool_name": "Bash", "agent_type": None})
    check("agent_type null: passes in silence", (r.returncode, r.stdout) == (0, b""), r.stdout)
    for bad in ("not json", "", "[1, 2]", '{"agent_type": "code-review"} {"agent_type": "x"}'):
        r = run(bad)
        check(f"payload {bad!r}: asks, never passes", r.returncode == 0 and decision(r).get("permissionDecision") == "ask",
              r.stdout)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
