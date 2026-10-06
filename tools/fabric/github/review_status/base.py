"""tools/fabric/github/review_status/base.py — the command's name, its refusal, its two streams and jq's way of printing values.
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
