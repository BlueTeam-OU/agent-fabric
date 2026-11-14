#!/usr/bin/env python3
"""tools/fabric/session_proc.py: the one rule for finding a session's claude process (j836), against a fake /proc of
each layout the harness has had, and the three walks that use it (status, gzcoord's session part, fabric-fresh's).

The old walk is kept below as `old_walk`, the rule every site had until j836, so each new-layout case also shows what
it returned there: a case that the old walk passes is no evidence the rule changed.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools", "fabric")
sys.path.insert(0, TOOLS)
import session_proc  # noqa: E402
import status  # noqa: E402
from gzcoord.inbox_parts import session as inbox_session  # noqa: E402

FAILS = 0


def check(name: str, ok: bool) -> None:
    global FAILS
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAILS += 1


def build(root: str, tree: dict) -> str:
    """tree: pid -> (comm, ppid, argv[, environ]); written as /proc/<pid>/{stat,cmdline,environ}."""
    for pid, spec in tree.items():
        comm, ppid, argv = spec[:3]
        d = os.path.join(root, str(pid))
        os.makedirs(d)
        with open(os.path.join(d, "stat"), "w", encoding="utf-8") as fh:
            fh.write(f"{pid} ({comm}) S {ppid} " + " ".join(["0"] * 17) + " 100 0 0\n")
        if argv is not None:
            with open(os.path.join(d, "cmdline"), "wb") as fh:
                fh.write(b"\0".join(a.encode() for a in argv) + b"\0")
        with open(os.path.join(d, "environ"), "wb") as fh:
            fh.write(spec[3] if len(spec) > 3 else b"")
    return root


def old_walk(start: int, proc: str) -> int | None:
    """What status.py, fresh.py, review_brief and the guard did: the nearest ancestor whose comm is `claude`."""
    pid = start
    for _ in range(64):
        st = session_proc.read_stat(pid, proc)
        if st is None or pid <= 1:
            return None
        if st[0] == "claude":
            return pid
        pid = st[1]
    return None


OLD = {1: ("systemd", 0, ["systemd"]),
       30: ("claude", 1, ["claude", "--model", "x"], b"CLAUDE_CODE_OAUTH_TOKEN=old\0"),
       40: ("bash", 30, ["bash"]), 50: ("fabric-python", 40, ["fabric-python"])}
# Claude Code 2.1.322: the daemon is `claude` too (cwd the home directory) and is the session's grandparent's parent.
NEW = {1: ("systemd", 0, ["systemd"]),
       100: ("claude", 1, ["claude", "daemon"], b"CLAUDE_CODE_OAUTH_TOKEN=daemon\0"),
       90: ("bg-pty-host", 100, ["bg-pty-host"]),
       80: ("2.1.322", 90, ["2.1.322", "--session-id", "abc"], b"CLAUDE_CODE_OAUTH_TOKEN=session\0"),
       70: ("bash", 80, ["bash"]), 60: ("fabric-python", 70, ["fabric-python"])}


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="session-proc-")
    try:
        old = build(os.path.join(tmp, "old"), OLD)
        new = build(os.path.join(tmp, "new"), NEW)

        print("the rule")
        check("old layout: the nearest claude is the session", session_proc.nearest_session(50, old) == 30)
        check("new layout: the session is the version-named process, not the daemon above it",
              session_proc.nearest_session(60, new) == 80)
        check("…and the old walk stops at the daemon (positive control: the case can fail)", old_walk(60, new) == 100)
        check("new layout: a walk that starts at the session counts it", session_proc.nearest_session(80, new) == 80)
        check("new layout: a walk that starts above the session finds none (the daemon is no session)",
              session_proc.nearest_session(90, new) is None and session_proc.nearest_session(100, new) is None)
        check("the daemon's `daemon` argument is what excludes it, not its place",
              session_proc.is_session(100, "claude", new) is False
              and session_proc.is_session(30, "claude", old) is True)
        check("a claude whose cmdline cannot be read stays a session (the older fixtures carry none)",
              session_proc.is_session(30, "claude", build(os.path.join(tmp, "nocmd"), {30: ("claude", 1, None)})) is True)
        check("an empty-argv claude is a session too", session_proc.is_session(30, "claude", build(os.path.join(tmp, "empty"), {30: ("claude", 1, [])})) is True)
        check("only a dotted three-part version is a version comm",
              all(session_proc.is_session(1, c, new) for c in ("2.1.322", "10.0.1"))
              and not any(session_proc.is_session(1, c, new) for c in ("2.1", "2.1.322-beta", "v2.1.322", "2.1.x", "claude2", "bash", "")))
        check("a named fake comm is matched exactly, and the version rule is off for it",
              session_proc.nearest_session(50, old, "bash") == 40 and session_proc.nearest_session(60, new, "claude-fake") is None
              and session_proc.nearest_session(60, new, "2.1.322") == 80)
        check("a process /proc does not show, or a loop, is None, never a neighbour",
              session_proc.nearest_session(999, new) is None
              and session_proc.nearest_session(5, build(os.path.join(tmp, "loop"), {5: ("a", 6, ["a"]), 6: ("b", 5, ["b"])})) is None)
        check("a comm with spaces and parentheses is read whole",
              session_proc.read_stat(7, build(os.path.join(tmp, "odd"), {7: ("a b) (c", 3, ["x"])})) == ("a b) (c", 3))

        print("status.harness_environ")
        check("old layout: the claude's environment", status.harness_environ(50, old) == {"CLAUDE_CODE_OAUTH_TOKEN": "old"})
        check("new layout: the session's environment, not the daemon's",
              status.harness_environ(60, new) == {"CLAUDE_CODE_OAUTH_TOKEN": "session"})
        check("no session above: None", status.harness_environ(90, new) is None)

        print("gzcoord inbox_parts/session.nearest_claude")
        check("old layout", getattr(inbox_session.nearest_claude(50, old), "pid", None) == 30)
        check("new layout: the session", getattr(inbox_session.nearest_claude(60, new), "pid", None) == 80)
        check("new layout: nothing above the daemon but init is no session", inbox_session.nearest_claude(90, new) is None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{FAILS} failed" if FAILS else "all ok")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
