#!/usr/bin/env python3
"""tools/fabric/session_proc.py — which process is a Claude Code session, and the walk up to it.

THE RULE (j836, 2026-11-14). A session's process is the nearest ancestor that is either
  - the harness under the older layout: comm `claude`, whose argv[1] is not `daemon`; or
  - the harness under 2.1.322's bg-pty-host layout: comm equal to the version (`2.1.322`, argv0 the same), sitting
    under bg-pty-host < `claude daemon` < ... .
WHY the daemon is excluded. Under the new layout the daemon is also comm `claude` (cwd the home directory, argv
`claude daemon ...`) and is an ancestor of every session. A walk that stops at the first comm `claude` stops there:
the wrong cwd for a review brief's clone check, the wrong environment for status, and a SIGTERM from `fabric-fresh`
that would end every session of the host's daemon, not the one that asked.

What is NOT known and so not decided here: a harness version whose comm is neither `claude` nor a dotted version
(it is not found: None, never a plausible neighbour). A comm `claude` whose cmdline cannot be read counts as a
session, as the walks did before this module (a same-login ancestor's cmdline is readable; the fixtures of the older
suites carry none); only a cmdline that says `daemon` removes it.

`proc` is the /proc root, so a test builds the tree it asks about. Everything is read from /proc; nothing is run."""
from __future__ import annotations

import os
import re

PROC = "/proc"
SESSION_COMM = "claude"
MAX_HOPS = 64
# comm is the kernel's name for the process, at most 15 bytes: a version fits.
VERSION_COMM = re.compile(r"\d+\.\d+\.\d+\Z")


def read_stat(pid: int, proc: str = PROC) -> tuple[str, int] | None:
    """(comm, ppid) from /proc/<pid>/stat, or None when the process is not there or the line is not one."""
    try:
        with open(f"{proc}/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    # The name sits in parentheses and may hold spaces and parentheses: the last `)` ends it.
    left, sep, right = text.rpartition(")")
    fields = right.split()
    if not sep or len(fields) < 2 or not fields[1].isdigit():
        return None
    return left.partition("(")[2], int(fields[1])


def read_argv(pid: int, proc: str = PROC) -> list[str] | None:
    try:
        with open(f"{proc}/{pid}/cmdline", "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    return [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]


def is_session(pid: int, comm: str, proc: str = PROC, session_comm: str = SESSION_COMM) -> bool:
    """Is process `pid`, whose comm is `comm`, a harness session? `session_comm` is the name looked for: the suites
    (fabric-fresh's AGENT_FABRIC_FRESH_COMM) look for a fake name, which is matched exactly and nothing else is."""
    if session_comm != SESSION_COMM:
        return comm == session_comm
    if VERSION_COMM.match(comm):
        return True
    if comm != SESSION_COMM:
        return False
    argv = read_argv(pid, proc)
    return not (argv and argv[1:2] == ["daemon"])


def nearest_session(start: int, proc: str = PROC, session_comm: str = SESSION_COMM) -> int | None:
    """The nearest session at `start` or above it, or None: no such ancestor, or /proc shows a break in the chain.
    `start` itself counts, so a caller that wants its ancestors passes its parent."""
    pid = start
    for _ in range(MAX_HOPS):
        if pid <= 1:
            return None
        stat = read_stat(pid, proc)
        if stat is None:
            return None
        if is_session(pid, stat[0], proc, session_comm):
            return pid
        pid = stat[1]
    return None

