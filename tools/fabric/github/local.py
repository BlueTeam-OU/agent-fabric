"""tools/fabric/github/local.py — the local questions the GitHub tools' lane
guards ask: which working copy, which host, which login, which role. Every
one is bounded (review of #71): a hung git — a lock, a network filesystem —
or a stuck helper used to hang the guard with no end. A question that finds
no answer in time answers nothing, and each guard already fails closed on
an empty answer."""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import git  # noqa: E402

PROBE_TIMEOUT_S = 30


def probe(cmd: list[str], timeout: float = PROBE_TIMEOUT_S) -> tuple[int, str]:
    """(exit status, stdout) of a command, as a shell would give them: 127
    and nothing when it is not there, 124 and nothing when it outlives its
    bound."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
    except OSError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    return r.returncode, r.stdout


def toplevel() -> str | None:
    """The working copy this process stands in, or None."""
    try:
        return git.toplevel(os.getcwd())
    except git.GitError:
        return None


def remote_url(root: str) -> str:
    """origin's URL in that working copy, or "" when it has none or git
    gives no answer."""
    try:
        r = git.run(root, "remote", "get-url", "origin", check=False)
    except git.GitError:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""
