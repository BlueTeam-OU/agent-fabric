#!/usr/bin/env python3
"""runtime/claude-code/hooks/pr-counts.py — a reply that states a pull
request's status carries its commit counts, or it goes back to the agent.

The owner decides whether to arm a pull request from what the agent says,
and asked, again and again, how many commits of each kind it held: the
rule "any PR status you state carries its counts" (team.md) did not hold
in prose (the owner, 2026-10-08: "everytime I have to ask, really
irritating"). Registered at user scope (runtime/claude-code/user-settings.py)
on Stop, so it runs for every session of the account.

On Stop it reads the reply the session is about to end on
(`last_assistant_message`). A line that names a pull request (`#123`,
`owner/repo#123`) beside a status word (arm, merge, ready, mergeable,
queued, gate, open, waiting, …) must also carry `(N work, M fix)`; fenced
code is not read. When a line does not, the reply is blocked once with
the reason: the session adds the counts from runtime/github/pr-gate.sh
and answers again. `stop_hook_active` (the session is already continuing
because of a stop hook) lets the second answer through whatever it says:
the guard asks once, and never holds a session in a loop.

The patterns are linear (no nested quantifiers): a hook past its timeout
does not refuse, it only costs the session time. Anything unexpected
lets the reply through; the guard never stands in a session's way.
"""
from __future__ import annotations

import json
import re
import sys

PR_RE = re.compile(r"(?<![\w/])(?:[\w.-]+/)?[\w.-]*#(\d{1,6})\b")
STATUS_RE = re.compile(r"\b(?:arm|armed|arming|merge|merged|mergeable|ready|queued|gate|waiting|"
                       r"your word|auto-merge|open|opened)\b", re.I)
COUNTS_RE = re.compile(r"\(\s*\d+\s+work\s*,\s*\d+\s+fix\b", re.I)
MAX_CHARS = 200_000


def missing(text: str) -> list[str]:
    """The pull-request numbers named on a status line that carries no counts."""
    out: list[str] = []
    in_fence = False
    for line in text[:MAX_CHARS].splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not STATUS_RE.search(line) or COUNTS_RE.search(line):
            continue
        for m in PR_RE.finditer(line):
            if m.group(0) not in out:
                out.append(m.group(0))
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or payload.get("stop_hook_active"):
            return 0
        text = payload.get("last_assistant_message")
        if not isinstance(text, str):
            return 0
        prs = missing(text)
        if prs:
            print(json.dumps({"decision": "block", "reason": (
                f"Your reply states the status of {', '.join(prs)} without its commit counts. The owner decides "
                "whether to arm from what you say: give each as \"#N (W work, F fix)\", read from "
                "runtime/github/pr-gate.sh (or the project's tools/gh/pr-gate.sh), and answer again.")}))
    except Exception:  # noqa: BLE001 - a guard on prose never stands in a session's way
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
