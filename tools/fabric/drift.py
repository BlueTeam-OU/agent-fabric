#!/usr/bin/env python3
"""tools/fabric/drift.py — two things an account can silently fall behind on, said by
`fabric-ctl <login|all> status` (each account's own control agent) and by `fabric-status`:

    harness(home, root)         the Claude Code installed here against runtime/claude-code/harness.json
    inbox(api, channel, me)     the account's GZCoord read position against the relay's newest message

Read-only, stdlib only (fabric-status starts on it, so it imports nothing of the control plane;
tests/test_drift.py holds its pin reader and binary path to control/upgrade.py's).

harness: {"status": "ok", "installed", "pinned", "drift"}. `pinned` is the checkout's
harness.json `claude` or null when it holds none (an unpinned fleet: drift is null, never False);
`drift` is installed != pinned, null when either is unknown. `claude --version` that cannot run,
or whose first word is not digits.digits.digits, is {"status": "failed", "error", "pinned"}: an
unknown version is never read as the pinned one.

inbox: the relay keeps one cursor per consumer (the account's address), moved only by an
acknowledgement; `GET /api/wait?...&timeout_seconds=0` lists what is past that cursor without
moving it (measured 2026-10-10: the same two messages twice; a caught-up cursor answers at once, 0.07 s,
not after a long poll). So the position is read from the
oldest message the account has not acknowledged:
  {"status": "ok", "channel", "unread", "capped", "oldest_unread_seq", "oldest_unread_at",
   "lag_s", "lagging", "newest_seq"}
`unread` counts messages past the cursor, all of them and not only those addressed to the account
(the watch acknowledges others' traffic as it passes it), up to one page, `capped` saying it was
full; `lag_s` the oldest one's age; `lagging` lag_s over a day (LAG_S). Nothing unread is lag 0.
An age that cannot be read is lag_s and lagging null. No GZCoord channel for the account's project
is {"status": "none", "reason"}. A relay that cannot be asked raises, and the caller says it failed.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import time
import sys
import urllib.parse
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import roots  # noqa: E402

LAG_S = 86400
PAGE = 50
VERSION_TIMEOUT_S = 10
# control/upgrade.py's VERSION_RE, ASCII digits only (that one takes any Unicode digit).
VERSION_RE = re.compile(r"\d{1,4}\.\d{1,4}\.\d{1,6}", re.ASCII)


def claude_bin(home: str) -> str:
    """The binary `fabric-ctl upgrade claude` installs and verifies (control/ops/usage.py's claude_bin): the
    account's own ~/.local/bin/claude, else whatever `claude` the PATH has."""
    own = os.path.join(home, ".local", "bin", "claude")
    return own if os.path.exists(own) else "claude"


def pinned_claude(root: str) -> str | None:
    try:
        with open(os.path.join(root, "runtime", "claude-code", "harness.json"), encoding="utf-8") as fh:
            v = json.load(fh).get("claude")
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, str) and VERSION_RE.fullmatch(v) else None


def harness(home: str | None = None, root: str | None = None, run: Callable[..., Any] = subprocess.run) -> dict:
    home = os.path.expanduser("~") if home is None else home
    root = root or roots.checkout_root(home)
    pinned = pinned_claude(root)
    binary = claude_bin(home)
    try:
        r = run([binary, "--version"], capture_output=True, text=True, errors="replace", timeout=VERSION_TIMEOUT_S, check=True,
                stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": f"claude --version: no answer within {VERSION_TIMEOUT_S} s", "pinned": pinned}
    except subprocess.CalledProcessError as e:
        return {"status": "failed", "error": f"claude --version: exit {e.returncode}", "pinned": pinned}
    except OSError as e:
        return {"status": "failed", "error": f"claude --version: {e.strerror or e}", "pinned": pinned}
    words = (r.stdout or "").split()
    installed = words[0] if words else None
    if installed is None or not VERSION_RE.fullmatch(installed):
        return {"status": "failed", "error": "claude --version said something that is not a version", "pinned": pinned}
    return {"status": "ok", "installed": installed, "pinned": pinned, "drift": None if pinned is None else installed != pinned}


def _messages(page: Any) -> list[dict]:
    rows = page.get("messages") if isinstance(page, dict) else page
    if not isinstance(rows, list) or not all(isinstance(m, dict) for m in rows):
        raise ValueError("the relay's answer carries no list of messages")
    return rows


def _seq(m: dict) -> int:
    s = m.get("seq")
    if not isinstance(s, int) or isinstance(s, bool):
        raise ValueError("a message without a seq")
    return s


def _stamp(m: dict) -> str | None:
    # /api/wait lists a message's time as ts and ts_full; /api/messages (and the oldest history) as timestamp.
    # Measured on the live relay 2026-10-10: reading only timestamp left every listed age unknown.
    return next((s for s in (m.get("ts_full"), m.get("timestamp"), m.get("ts")) if isinstance(s, str)), None)


def _age_s(stamp: Any, now: float) -> int | None:
    if not isinstance(stamp, str):
        return None
    try:
        then = datetime.datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if then.tzinfo is None:
        return None
    return max(0, int(now - then.timestamp()))


def inbox(api: Callable[..., Any], channel: str | None, me: str, now: float | None = None, page: int = PAGE) -> dict:
    if not channel:
        return {"status": "none", "reason": "no GZCoord channel for this account's project"}
    now = time.time() if now is None else now
    unread = _messages(api("/api/wait?" + urllib.parse.urlencode(
        {"channel": channel, "consumer_id": me, "timeout_seconds": "0", "limit": str(page)})))
    newest = _messages(api("/api/messages?" + urllib.parse.urlencode({"channel": channel, "limit": "1"})))
    newest_seq = max((_seq(m) for m in newest), default=None)
    out: dict[str, Any] = {"status": "ok", "channel": channel, "unread": len(unread), "capped": len(unread) >= page,
                           "oldest_unread_seq": None, "oldest_unread_at": None, "lag_s": 0, "lagging": False, "newest_seq": newest_seq}
    if unread:
        oldest = min(unread, key=_seq)
        at = _stamp(oldest)
        lag = _age_s(at, now)
        out.update(oldest_unread_seq=_seq(oldest), oldest_unread_at=at, lag_s=lag,
                   lagging=None if lag is None else lag > LAG_S)
    return out
