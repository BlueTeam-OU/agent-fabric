"""tools/fabric/github/pr_gate_base.py — what pr_gate and the modules split out
of it share: the usage exception, the stderr note, jq's `//` and string
interpolation, a git call read as "no" on any failure, and the two caps.
Split out of pr_gate.py, unchanged."""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import git  # noqa: E402

LIST_CAP = 500


INFLIGHT_PATHS_CAP = 200   # a row's paths as data; the total is always given


class Usage(Exception):
    pass


def note(msg: str) -> None:
    print(f"pr-gate: {msg}", file=sys.stderr)


def alt(*values):
    """jq's `a // b`: the first value that is neither null nor false."""
    for v in values:
        if v is not None and v is not False:
            return v
    return None


def jq_str(v) -> str:
    """A value as jq's string interpolation writes it."""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def succeeds(*args: str) -> bool:
    """A git call read as the bash read it: any failure is "no". git.ok
    raises on a status other than 0 or 1, and a failed fetch is 128."""
    try:
        return git.run(".", *args, check=False).returncode == 0
    except git.GitError:
        return False
