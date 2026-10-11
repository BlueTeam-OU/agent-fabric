#!/usr/bin/env python3
"""tools/fabric/fleet_proc.py — what each login's processes cost this host:
CPU%, RSS, swap and process count, read from /proc (Fleet Deck, the C0
cost class; fleet.py asks for it locally, or through the host executor for
a host this checkout is not on).

CONTRACT
  argv      --json [--login L]… [--interval S] [-h|--help]
            --json is required: a human table is a later, separate mode.
            --login narrows to those logins (default: every placed login of
            this host, from the hosts registry); --interval is the gap
            between the two CPU samples (default 1.0, 0 to 30).
  stdout    one JSON object: {"host", "at", "interval_s", "agents": {login:
            {"uid", "cpu_pct", "rss_kb", "swap_kb", "procs", "inbox_watch"}}}
            — a login with no process is present with zeros (cpu_pct is null
            when no time passed between the samples), a login the host has no
            account for is absent from "agents" and listed in "unknown".
            inbox_watch is true when a process of the login runs
            gzcoord-inbox with --until-delivery or --wait; false when its
            processes were read and none does; null when that could not be
            told (a process's command line unreadable, or /proc hides other
            accounts' processes from this reader): never false for unknown.
  stderr    one `fleet_proc: ` line on a refusal.
  exit      0 read; 2 usage or an unreadable registry.

WHAT IT READS, AND NEVER
  /proc/<pid>/stat (CPU ticks) and /proc/<pid>/status (Uid, VmRSS,
  VmSwap), and /proc itself to list the pids, and /proc/mounts for the
  hidepid option. Never environ, maps or fd: an agent's environment holds
  its credentials. A process's command line is read once, in the second
  sample, for the first CMDLINE_BYTES bytes of the processes of the logins
  asked about, and only to answer one question — does it run gzcoord-inbox
  with --until-delivery or --wait — by whole arguments (a prompt or a shell
  string that merely contains the words is not a watch). What it said is
  never kept, printed or returned: the answer is a boolean.

  A process is attributed to its EFFECTIVE uid, the one `ps -u` selects by,
  so a login's total here and `ps -o rss= -u <login>` summed are the same
  set. CPU% is the ticks the processes present in BOTH samples used, over
  the wall time between them, 100 = one core; a process that started or
  exited between the samples contributes to rss and the count but not to
  CPU, because a half-observed life is not a rate.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pwd
import socket
import sys
import time
from collections.abc import Callable

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import roots  # noqa: E402

DEFAULT_INTERVAL_S = 1.0
MAX_INTERVAL_S = 30.0
# The words of a watch are in the first few arguments; the rest of a command line (a session's prompt) is not looked at.
CMDLINE_BYTES = 4096
WATCH_COMMAND = "gzcoord-inbox"
WATCH_OPTIONS = ("--until-delivery", "--wait")

HELP = """usage: fleet_proc.py --json [--login L]... [--interval S]

Per-login CPU%, RSS, swap and process count for this host, from /proc.
Reads /proc/<pid>/stat and /proc/<pid>/status only."""


class Sample:
    """One pass over /proc: per effective uid, the processes' CPU ticks and
    their memory."""

    def __init__(self) -> None:
        self.ticks: dict[int, dict[int, int]] = {}   # uid -> pid -> utime+stime
        self.rss_kb: dict[int, int] = {}
        self.swap_kb: dict[int, int] = {}
        self.procs: dict[int, int] = {}
        # Only when the command lines were asked for (sample(..., cmdlines=True)): the uids with a watch, and the
        # uids with a process whose command line could not be read.
        self.watching: set[int] = set()
        self.unreadable: set[int] = set()
        self.hidden: bool | None = None   # whether /proc hides other accounts' processes from this reader


def parse_stat_ticks(text: str) -> int:
    """utime + stime from a /proc/<pid>/stat line. The command is field 2,
    parenthesised and free to contain spaces and parentheses, so the fields
    are counted from the LAST `)`."""
    rest = text[text.rindex(")") + 2:].split()
    # rest[0] is field 3 (state); utime is field 14, stime 15.
    return int(rest[11]) + int(rest[12])


def parse_status(text: str) -> dict[str, int]:
    """The effective uid and the memory a /proc/<pid>/status line set gives;
    a kernel thread has no VmRSS or VmSwap and reads 0."""
    out = {"euid": -1, "rss_kb": 0, "swap_kb": 0}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key == "Uid":
            out["euid"] = int(value.split()[1])
        elif key == "VmRSS":
            out["rss_kb"] = int(value.split()[0])
        elif key == "VmSwap":
            out["swap_kb"] = int(value.split()[0])
    if out["euid"] < 0:
        raise ValueError("no Uid line")
    return out


def runs_inbox_watch(raw: bytes) -> bool:
    """Whether a command line (NUL-separated, as /proc gives it) is `gzcoord-inbox` run with --until-delivery or --wait:
    the command among its first arguments (after an interpreter and its flags: `fabric-python -I <path>/gzcoord-inbox
    --until-delivery`) and the option as a whole argument. A longer argument that contains the words is not one."""
    argv = [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]
    return (any(os.path.basename(a) == WATCH_COMMAND for a in argv[:4])
            and any(a in WATCH_OPTIONS for a in argv[1:8]))


def proc_hides_others(proc: str, euid: int | None = None, groups: list[int] | None = None) -> bool | None:
    """Whether this reader cannot see other accounts' processes: /proc mounted with hidepid hiding them (1 or noaccess,
    2 or invisible, 4 or ptraceable) from a reader that is neither root nor in the `gid=` group. None when the mount
    options cannot be read — unknown, which a caller does not read as "sees all"."""
    try:
        with open(os.path.join(proc, "mounts"), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    for line in lines:
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "/proc":
            options = dict(o.partition("=")[::2] for o in parts[3].split(","))
            hidepid = options.get("hidepid", "0")
            if hidepid in ("0", "off", ""):
                return False
            gid = options.get("gid")
            if (os.geteuid() if euid is None else euid) == 0 or (gid and gid.isdigit() and int(gid) in (os.getgroups() if groups is None else groups)):
                return False
            return True
    return None


def sample(uids: set[int], proc: str = "/proc", cmdlines: bool = False) -> Sample:
    s = Sample()
    if cmdlines:
        s.hidden = proc_hides_others(proc)
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open(os.path.join(proc, name, "status"), encoding="ascii", errors="replace") as fh:
                st = parse_status(fh.read())
            if st["euid"] not in uids:
                continue
            with open(os.path.join(proc, name, "stat"), encoding="ascii", errors="replace") as fh:
                ticks = parse_stat_ticks(fh.read())
        except (OSError, ValueError, IndexError):
            continue   # gone since the listing, or not ours to read: not a process to count
        uid = st["euid"]
        if cmdlines:
            try:
                with open(os.path.join(proc, name, "cmdline"), "rb") as fh:
                    if runs_inbox_watch(fh.read(CMDLINE_BYTES)):
                        s.watching.add(uid)
            except (FileNotFoundError, ProcessLookupError):
                continue   # exited since its status was read: not a process to count
            except OSError:
                s.unreadable.add(uid)
        s.ticks.setdefault(uid, {})[pid] = ticks
        s.rss_kb[uid] = s.rss_kb.get(uid, 0) + st["rss_kb"]
        s.swap_kb[uid] = s.swap_kb.get(uid, 0) + st["swap_kb"]
        s.procs[uid] = s.procs.get(uid, 0) + 1
    return s


def cpu_pct(first: dict[int, int], second: dict[int, int], seconds: float, clk_tck: int) -> float | None:
    """100 = one core busy for the whole interval. Only pids in both samples.
    None when no time passed: an unmeasured rate is not an idle agent."""
    if seconds <= 0:
        return None
    used = sum(max(0, second[p] - first[p]) for p in first.keys() & second.keys())
    return round(100.0 * used / clk_tck / seconds, 1)


def watch_state(uid: int, s: Sample, own_uid: int) -> bool | None:
    """True with a watch seen; None when the processes could not all be read (a command line refused, or /proc hiding
    or not saying whether it hides other accounts' processes: an account that may be invisible is not one with none);
    False only for processes that were read and are not one."""
    if uid in s.watching:
        return True
    if uid in s.unreadable:
        return None
    if uid != own_uid and s.hidden is not False:
        return None
    return False


def collect(logins: list[str], interval: float = DEFAULT_INTERVAL_S, *, proc: str = "/proc",
            uid_of: Callable[[str], int] | None = None, clk_tck: int | None = None,
            clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
            host: str | None = None, now: Callable[[], dt.datetime] | None = None, own_uid: int | None = None) -> dict:
    lookup = uid_of or (lambda login: pwd.getpwnam(login).pw_uid)
    uids: dict[str, int] = {}
    unknown: list[str] = []
    for login in logins:
        try:
            uids[login] = lookup(login)
        except KeyError:
            unknown.append(login)
    wanted = set(uids.values())
    tck = clk_tck or os.sysconf("SC_CLK_TCK")
    own = os.geteuid() if own_uid is None else own_uid
    t0 = clock()
    first = sample(wanted, proc)
    sleep(interval)
    second = sample(wanted, proc, cmdlines=True)
    seconds = clock() - t0
    agents = {}
    for login, uid in uids.items():
        agents[login] = {
            "uid": uid,
            "cpu_pct": cpu_pct(first.ticks.get(uid, {}), second.ticks.get(uid, {}), seconds, tck),
            "rss_kb": second.rss_kb.get(uid, 0),
            "swap_kb": second.swap_kb.get(uid, 0),
            "procs": second.procs.get(uid, 0),
            "inbox_watch": watch_state(uid, second, own),
        }
    stamp = (now or (lambda: dt.datetime.now(dt.UTC)))().strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"host": host if host is not None else roots_host(), "at": stamp, "interval_s": interval,
            "agents": agents, "unknown": unknown}


def roots_host() -> str:
    # The registry id of a host is its short hostname (ADR-010); the same
    # reading as runtime/identity.py's current_host, which is loaded by path
    # and not imported, so this file runs on a host with nothing else of ours.
    return socket.gethostname().split(".")[0]


def placed_here(registry: str, host: str) -> list[str]:
    with open(registry, encoding="utf-8") as fh:
        reg = json.load(fh)
    placement = reg.get("placement")
    if not isinstance(placement, dict):
        raise ValueError("no placement object")
    return sorted(login for login, h in placement.items() if h == host)


def main(argv: list[str]) -> int:
    logins: list[str] = []
    interval = DEFAULT_INTERVAL_S
    as_json = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(HELP)
            return 0
        if a == "--json":
            as_json = True
        elif a in ("--login", "--interval"):
            if i + 1 >= len(argv):
                print(f"fleet_proc: {a} needs a value", file=sys.stderr)
                return 2
            i += 1
            if a == "--login":
                logins.append(argv[i])
            else:
                try:
                    interval = float(argv[i])
                except ValueError:
                    interval = -1.0
                if not 0 <= interval <= MAX_INTERVAL_S:
                    print(f"fleet_proc: --interval is a number of seconds from 0 to {MAX_INTERVAL_S:g}", file=sys.stderr)
                    return 2
        else:
            print(f"fleet_proc: unknown argument {a}", file=sys.stderr)
            return 2
        i += 1
    if not as_json:
        print("fleet_proc: --json is required", file=sys.stderr)
        return 2
    host = roots_host()
    if not logins:
        try:
            logins = placed_here(roots.hosts_registry(), host)
        except (OSError, ValueError) as e:
            print(f"fleet_proc: cannot read the hosts registry: {e}", file=sys.stderr)
            return 2
    print(json.dumps(collect(logins, interval, host=host)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
