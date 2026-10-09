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
(`last_assistant_message`). A pull request (`#123`, `owner/repo#123`)
named on a line with a status word (arm, merge, ready, unarmed, queued,
gate, open, waiting, …) must carry `N work, M fix` (parentheses optional)
after it on its line, before the next PR, at least once in the reply;
fenced and inline code are not read, and a number that is an issue, a
step, an item or a colour is not a PR. When a
pull request lacks them, the reply is blocked once with the reason: the
session adds the counts from fabric-pr gate and answers again. `stop_hook_active` (the session is already continuing
because of a stop hook) lets the second answer through whatever it says:
the guard asks once, and never holds a session in a loop.

Every pattern runs in linear time (see NUM_RE): a hook past its timeout
does not refuse, it only costs the session time. Anything unexpected
lets the reply through; the guard never stands in a session's way.
"""
from __future__ import annotations

import json
import re
import sys

# Every pattern is linear: `#N` is found on its own, and what may precede it
# is read from at most PREFIX characters before it, so no match can start
# at every character of a long run (an earlier "[\w.-]+/)?[\w.-]*#" was
# quadratic on a line of dashes, review of #117).
NUM_RE = re.compile(r"#(\d{1,5})(?!\d)")
PREFIX = 120
OWNER_REPO_RE = re.compile(r"[\w.-]{1,60}/[\w.-]{1,60}")
NOT_A_PR_WORDS = frozenset(("issue", "issues", "step", "steps", "item", "items", "no", "no.", "number",
                            "line", "rule", "row", "seq", "round"))
STATUS_RE = re.compile(r"\b(?:arm|armed|arming|unarmed|merge|merged|mergeable|ready|queued|gate|waiting|"
                       r"your word|auto-merge|open|opened)\b", re.I)
# A PR's counts are "W work, F fix", parenthesised or not (team.md's own
# example is "#215 is unarmed: 6 work, 2 fix"), anywhere after it on its
# line and before the next PR: emphasis, a colon or a table's cells may come
# between.
COUNTS_RE = re.compile(r"\b\d{1,4}\s+work\s*,\s*\d{1,4}\s+fix\b", re.I)
CODE_SPAN_RE = re.compile(r"`[^`\n]*`")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
MAX_CHARS = 200_000


def prose_lines(text: str):
    """The lines outside fenced code, inline code spans removed. A fence
    closes only on the character that opened it, at least as long."""
    fence = ""
    for line in text[:MAX_CHARS].splitlines():
        m = FENCE_RE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not line.strip()[len(m.group(1)):]:
                fence = ""
            continue
        # A backtick run with another backtick later on the line is a code
        # span (```a```), not a fence: CommonMark forbids one in the info string.
        if m and not (m.group(1)[0] == "`" and "`" in line.strip()[len(m.group(1)):]):
            fence = m.group(1)
            continue
        yield CODE_SPAN_RE.sub(" ", line)


def pr_ref(line: str, m: re.Match) -> str | None:
    """The pull request `#N` names, as written (`#N` or `owner/repo#N`), or
    None when the number is not a pull request: an issue, a step or an item
    (by the word before it), a colour (six digits: NUM_RE stops at five),
    or a number glued to a word. Only the token right before `#` is looked
    at, so each `#N` costs a constant (missing() keeps the rest linear)."""
    before = line[max(0, m.start() - PREFIX):m.start()]
    after = line[m.end():m.end() + 2]
    # A word character glued after the number makes it not a PR, except a
    # closing emphasis underscore (_#115_), which no word character follows.
    if after[:1].isalnum() or (after[:1] == "_" and after[1:2].isalnum()):
        return None
    glued = before[-1:] if before else ""
    repo = ""
    if glued and (glued.isalnum() or glued in "_.-/"):
        token = before.split()[-1] if before.split() else ""
        token = token.lstrip("*_|([{<'\"`~>-")
        # Only markup before # (_#115_, -#115): a plain PR.
        if token and not OWNER_REPO_RE.fullmatch(token):
            return None
        repo = token
    words = before.split()
    if words and words[-1].lower().strip("*_:") in NOT_A_PR_WORDS:
        return None
    return repo + m.group(0)


def missing(text: str) -> list[str]:
    """The pull requests whose status a line states with no "W work, F fix"
    after them on their line, before the next PR, unless the same pull
    request carries its counts somewhere in the reply."""
    stated: dict[str, None] = {}   # insertion-ordered, constant-time membership
    counted: set[str] = set()
    for line in prose_lines(text):
        status = bool(STATUS_RE.search(line))
        refs = [(m, r) for m in NUM_RE.finditer(line) if (r := pr_ref(line, m)) is not None]
        for i, (m, ref) in enumerate(refs):
            end = refs[i + 1][0].start() if i + 1 < len(refs) else len(line)
            if COUNTS_RE.search(line, m.end(), end):
                counted.add(ref)
            elif status:
                stated.setdefault(ref, None)
    return [r for r in stated if r not in counted]


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
                "fabric-pr gate in that project's working copy, and answer again.")}))
    except Exception:  # noqa: BLE001 - a guard on prose never stands in a session's way
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
