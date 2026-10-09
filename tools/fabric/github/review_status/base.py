"""tools/fabric/github/review_status/base.py — the command's name, its refusal, its two streams, jq's way of printing values,
and the one rule GraphQL answers are read by (listed, obj; pr_gate reads by it too).
A part of tools/fabric/github/pr_review_status.py, whose docstring is the contract."""
from __future__ import annotations

import json
import sys


PROG = "pr-review-status"


class Die(Exception):
    """A refusal: the message is the stderr text, verbatim, after the
    `pr-review-status: ` prefix; `code` is the exit (2 unless said)."""

    def __init__(self, msg: str, code: int = 2):
        super().__init__(msg)
        self.code = code


def out(text: str = "", end: str = "\n") -> None:
    sys.stderr.flush()
    sys.stdout.write(text + end)
    sys.stdout.flush()


def err(text: str) -> None:
    sys.stdout.flush()
    print(text, file=sys.stderr, flush=True)


# ── jq's reading of values, where the report prints them ────────────────

def jstr(v) -> str:
    """A value as jq's string interpolation (and `jq -r`) prints it: null
    is the word null, a string is itself."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def sha8(v):
    """`.commit_id[0:8]`: null stays null."""
    return None if v is None else v[:8]


def jkey(v):
    """jq's sort order for a timestamp that may be null: null first."""
    return (v is not None, "" if v is None else v)


def login_of(row: dict):
    return (row.get("user") or {}).get("login")


# GitHub's GraphQL answers, read by one rule: null is none (an empty list,
# an empty object), a value of the expected shape is itself, anything else
# is unreadable (None) — never a count of what could be read. A string's
# characters or a dict's keys taken as items once read as zero threads.
def listed(nodes) -> list[dict] | None:
    """A GraphQL connection's nodes: a list of objects, null (none), or —
    anything else, a non-object element included — None, unreadable,
    never zero."""
    if nodes is None:
        return []
    if isinstance(nodes, list) and all(isinstance(n, dict) for n in nodes):
        return nodes
    return None


def obj(value) -> dict | None:
    """A GraphQL object field: an object, null (an empty one), or —
    anything else — None, unreadable."""
    if value is None:
        return {}
    return value if isinstance(value, dict) else None
