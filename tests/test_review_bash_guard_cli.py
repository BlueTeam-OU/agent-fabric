#!/usr/bin/env python3
"""The oracle for the review class's Bash fence: runtime/claude-code/hooks/
review-bash-guard.sh (the shim) and review-bash-guard.py beside it, the fence
around the review class, which runs unisolated in the session clone.

Two things held still: state-changing git, installs and printing the
environment or secret material are DENIED however they are spelled (leading
whitespace, chained after another command, sudo, global git flags, quotes,
continuations), and read-only git, validators, guards and no-install builds
are ALLOWED -- a fence that blocks the review's own tools is a fence the next
session removes. The decision table is tests/fixtures/
review-bash-guard-cases.json, one real payload piped through the real shim per
case; what a table cannot hold is here: the guard judged in time on crafted
input, and a guard that cannot run, runs late or dies denying.

Ported from runtime/claude-code/hooks/test_review-bash-guard.sh when its cases
took it past ADR-040's 150 lines; the cases were extracted from it as bash
expanded them, never retyped.

The hook under test is $REVIEW_BASH_GUARD, default the shim.
Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = os.path.abspath(os.environ.get("REVIEW_BASH_GUARD") or os.path.join(
    HERE, "runtime", "claude-code", "hooks", "review-bash-guard.sh"))
CASES = os.path.join(HERE, "tests", "fixtures", "review-bash-guard-cases.json")
if not os.path.isfile(UNDER_TEST):
    sys.exit(f"test: not found: {UNDER_TEST}")

failures = 0


def check(label: str, good: bool, detail: str = "") -> None:
    global failures
    if good:
        print(f"  ok   {label}")
        return
    failures += 1
    print(f"  FAIL {label}: {detail}" if detail else f"  FAIL {label}")


def base_env(**extra: str) -> dict[str, str]:
    # The runner may be a fabric-launched session: its launch variables are
    # removed, never inherited; a case sets its own on purpose. The fleet's
    # Python is the shim's default, so AGENT_FABRIC_PYTHON passes through.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AGENT_FABRIC_", "CLAUDE_", "GZCOORD_")) or k == "AGENT_FABRIC_PYTHON"}
    env.update(extra)
    return env


def run(payload: str, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", UNDER_TEST], input=payload, capture_output=True, text=True,
                          env=base_env(**extra), timeout=60)


def decision(command: str, **extra: str) -> str:
    r = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "agent_type": "code-review"}), **extra)
    if not r.stdout.strip():
        return "allow"
    try:
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]
    except (ValueError, KeyError, TypeError):
        return "malformed"


def expect(label: str, want: str, command: str, **extra: str) -> None:
    got = decision(command, **extra)
    check(label, got == want, f"want {want}, got {got} for: {command}")


def table() -> None:
    with open(CASES, encoding="utf-8") as f:
        doc = json.load(f)
    for sec in doc["sections"]:
        print(sec["section"])
        for c in sec["cases"]:
            label = c.get("label") or ("denied: " if c["want"] == "deny" else "allowed: ") + c["command"]
            expect(label, c["want"], c["command"])


def in_time() -> None:
    # Python's re backtracks where grep did not, and a hook past its timeout
    # does not refuse: each shape below once ran for minutes (CodeQL on #96,
    # and a misplaced lookahead the fuzz caught). Allowed means judged in time:
    # a late verdict would have been a deny.
    print("Python backtracks where grep did not: a crafted command is judged in time (CodeQL on #96)")
    shapes = {
        "git followed by 3000 options": "git" + "\t--" * 3000 + "!",
        "env -C -- repeated 3000 times, then text": "env\t" + "-C\t--\t" * 3000 + "!",
        "git -A repeated 3000 times, then text": "git\t-A" + "\t-A" * 3000 + "!",
        "the word git 20000 times": "git " * 20000 + "x",
        "git -C -C repeated 3000 times, then text": "git" + " -C -C" * 3000 + "!",
        "git --attr-source repeated 3000 times, then text": "git" + " --attr-source" * 3000 + "!",
    }
    for label, command in shapes.items():
        expect(f"allowed in time: {label}", "allow", command)


def fails_closed() -> None:
    print("a guard that cannot run, runs late or dies denies; it never silently allows")
    expect("with the fleet's Python unavailable the guard denies, even a harmless command", "deny", "ls",
           AGENT_FABRIC_PYTHON="/nonexistent")
    expect("a module that fails (any exit but 0) is a deny, even for ls", "deny", "ls",
           AGENT_FABRIC_PYTHON="/bin/false")
    expect("a verdict later than the budget is a deny, even for ls", "deny", "ls",
           AGENT_FABRIC_REVIEW_GUARD_BUDGET="0")
    print("malformed input allows and never exits 2")
    for payload in ("{}", "not json", ""):
        r = run(payload)
        check(f"payload ({payload or 'empty'}) allows (rc={r.returncode})",
              r.returncode != 2 and not r.stdout.strip(), f"rc={r.returncode} out=[{r.stdout}]")


def main() -> int:
    table()
    in_time()
    fails_closed()
    print()
    if failures:
        print(f"{failures} assertion(s) failed", file=sys.stderr)
        return 1
    print("all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
