#!/usr/bin/env python3
"""runtime/claude-code/hooks/context-sample.py — the share of its context window a session has used, kept where
the account's control agent reads it (fleet-deck-attention s3).

Called by statusline.sh with the status line's JSON on stdin: no hook payload carries the context window's use,
the status line's input does (`context_window.used_percentage`: input, cache-read and cache-write tokens over
the window; null early in a session and after /compact). Keeps, per session id, in
<state>/session-context.json (the directory session-state.py names), mode 0600:

    {"sessions": {"<id>": {"pct": 0..100, "at": "<ISO UTC>"}}}

A value that is not a number in 0..100 writes nothing and leaves the last sample, so `at` says how old it is:
unknown is never 0. The status line redraws on every message, so the file is rewritten only when the whole
percentage has moved REWRITE_POINTS from the one kept, or the kept one is REFRESH_S old: each rewrite is a state
record the control agent posts to the relay. Entries older than KEEP_S are dropped when the file is written (a
killed session never says it ended).

The status line must never wait on this: any failure is swallowed, nothing is printed, the exit is 0, the lock is
not waited for. It reaches nothing but that one file.
"""
from __future__ import annotations

import calendar
import fcntl
import importlib.util
import json
import math
import os
import sys
import time

FILE = "session-context.json"
REWRITE_POINTS = 5
REFRESH_S = 300
KEEP_S = 24 * 3600


def _state_dir() -> str:
    # One definition of where the account's state lives: session-state.py's.
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session-state.py")
    spec = importlib.util.spec_from_file_location("session_state", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.state_dir()


def sample_of(payload: object) -> tuple[str, int] | None:
    """(session id, whole percentage) the status line's JSON gives, or None when it gives no usable one."""
    if not isinstance(payload, dict):
        return None
    sid = payload.get("session_id")
    window = payload.get("context_window")
    pct = window.get("used_percentage") if isinstance(window, dict) else None
    if not isinstance(sid, str) or not sid or isinstance(pct, bool) or not isinstance(pct, (int, float)):
        return None
    if not math.isfinite(pct) or not 0 <= pct <= 100:
        return None
    return sid, int(round(pct))


def _parse_at(text: object) -> float | None:
    try:
        return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ")) if isinstance(text, str) else None
    except ValueError:
        return None


def record(payload: object, directory: str | None = None, now: float | None = None) -> bool:
    """True when the file changed."""
    got = sample_of(payload)
    if got is None:
        return False
    sid, pct = got
    now = time.time() if now is None else now
    directory = directory or _state_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = os.path.join(directory, FILE)
    with open(os.path.join(directory, FILE + ".lock"), "a") as held:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            kept = doc.get("sessions") if isinstance(doc, dict) and isinstance(doc.get("sessions"), dict) else {}
        except (OSError, ValueError):
            kept = {}
        old = kept.get(sid) if isinstance(kept.get(sid), dict) else {}
        then = _parse_at(old.get("at"))
        if (isinstance(old.get("pct"), int) and then is not None and now - then < REFRESH_S
                and abs(pct - old["pct"]) < REWRITE_POINTS and then <= now):
            return False
        kept[sid] = {"pct": pct, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))}
        kept = {k: v for k, v in kept.items() if k == sid or (isinstance(v, dict) and (_parse_at(v.get("at")) or 0) > now - KEEP_S)}
        tmp = f"{path}.{os.getpid()}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"sessions": kept}, fh, sort_keys=True)
        os.replace(tmp, path)
        return True


def main() -> int:
    try:
        record(json.loads(sys.stdin.read() or "{}"))
    except Exception:  # noqa: BLE001 — the status line is never kept waiting or made noisy by this
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
