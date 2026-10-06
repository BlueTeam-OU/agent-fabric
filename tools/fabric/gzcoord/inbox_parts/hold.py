"""tools/fabric/gzcoord/inbox_parts/hold.py — the inbox held while its session plans, and the holder's life.
A part of tools/fabric/gzcoord/inbox.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
import re
import stat
from typing import Callable
from .. import i18n
from .. import jsvalues as js
from ..gzmsg import en


# ── THE HOLD (2026-09-16) ────────────────────────────────────────────
# A plan is written from the context the session had when it entered plan
# mode; a delivery mid-plan is context it was not asked to absorb. The
# harness cannot pause notifications, but a delivery is one only because
# this watch polls and prints — so while the session plans, the watch does
# not poll. The plan-hold hook writes <pid>.json under the login's own
# hold directory; the account is held while ANY marker names a live harness
# of this login: the pid answers a signal as this uid (EPERM is another
# login's process) and, when both sides know it, has the start time the
# marker recorded (a reused pid is not the harness). The directory and each
# file must be this login's — another login must not hold or release this
# inbox. Held is a line on stderr, never stdout.

def hold_dir(home: str | None = None) -> str:
    return os.environ.get("AGENT_FABRIC_HOLD_DIR",
                          os.path.join(os.path.expanduser("~") if home is None else home, ".cache", "agent-fabric", "hold"))


def pid_start(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            fields = re.sub(r".*\) ", "", fh.read(), count=1, flags=re.S).split(" ")
    except OSError:
        return ""
    return fields[19] if len(fields) > 19 else ""


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, OverflowError, ValueError):
        return False
    return True


def hold_status(directory: str | None = None, is_alive: Callable[[int], bool] = pid_alive,
                start_of: Callable[[int], str] = pid_start, uid: int | None = None,
                t: i18n.Printer | None = None) -> dict:
    directory = hold_dir() if directory is None else directory
    uid = os.getuid() if uid is None else uid
    t = t or en()
    try:
        st = os.lstat(directory)
    except OSError:
        return {"held": False, "reason": t("held.no-directory"), "sessions": []}
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        return {"held": False, "reason": t("held.not-a-directory"), "sessions": []}
    if st.st_uid != uid:
        return {"held": False, "reason": t("held.not-this-login"), "sessions": []}
    sessions, stale = [], []
    for name in os.listdir(directory):
        if not re.fullmatch(r"\d+\.json", name, re.ASCII):
            continue
        file = os.path.join(directory, name)
        try:
            if os.lstat(file).st_uid != uid:
                stale.append(t("held.stale-not-this-login", {"name": name}))
                continue
            with open(file, encoding="utf-8") as fh:
                m = json.load(fh)
        except (OSError, ValueError):
            stale.append(t("held.stale-unreadable", {"name": name}))
            continue
        m = m if isinstance(m, dict) else {}
        pid = m.get("pid")
        whole = (isinstance(pid, int) and not isinstance(pid, bool)) or (isinstance(pid, float) and pid.is_integer())
        if not whole or pid <= 0:
            stale.append(t("held.stale-no-pid", {"name": name}))
            continue
        pid = int(pid)
        if not is_alive(pid):
            stale.append(t("held.stale-gone", {"name": name, "pid": pid}))
            continue
        now = start_of(pid)
        if m.get("start") and now and js.string(m["start"]) != js.string(now):
            stale.append(t("held.stale-reused", {"name": name, "pid": pid}))
            continue
        sessions.append({"pid": pid, "session_id": m.get("session_id"), "since": m.get("since")})
    if not sessions:
        return {"held": False, "reason": "; ".join(stale) if stale else t("held.no-marker"), "sessions": sessions}
    return {"held": True, "sessions": sessions}


HOLD_POLL_MS = 1000
