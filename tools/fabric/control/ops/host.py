"""tools/fabric/control/ops/host.py — the machine the account shares, and the account's own home measured.
A part of the ops package, whose __init__.py is the contract every
extractor here keeps."""
from __future__ import annotations

import errno
import math
import os
import re
import stat
import subprocess
from typing import Any, Callable

from . import util
from gzcoord import jsvalues as js  # noqa: E402 — util puts tools/fabric on sys.path

LEASE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
LEASE_LABEL = re.compile(r"\(([A-Za-z0-9._-]{1,64})\)$")
CMD_TIMEOUT_S = 5


def _mb(kb: float | None) -> int | None:
    if kb is None or kb != kb:   # NaN is no number: null on the wire, as JSON.stringify said it
        return None
    return util.js_round(kb / 1024)


def _read(file: str) -> str | None:
    try:
        with open(file, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def host(proc: str = "/proc", sys: str = "/sys", leases: str = "/run/lock/agent-fabric",
         run: Callable[..., Any] = subprocess.run, cpus: int | None = None,
         statfs: Callable[[str], os.statvfs_result] = os.statvfs) -> dict:
    """The MACHINE this account shares — what develop-qzapp's crash of
    2026-09-19 was diagnosed from by hand, after the fact, with free, df,
    xenstore-read and find (docs/live-checks/2026-09-19-develop-qzapp-crash.md;
    the layers: ADR-010). Load and cpus; memory and swap from
    /proc/meminfo; the Xen balloon where there is one (current and target
    from sysfs, static-max — the ceiling this boot — from xenstore, null on
    a host that is not a Xen guest); every mounted block device once, by
    statfs; the leases held under /run/lock/agent-fabric, each probed with
    a read-only flock (held or not is the kernel's answer, the record line
    only says by whom); the largest processes by RSS, with the login they
    run as. Numbers and names of programs and logins, never a command
    line. Every daemon on one host answers the same numbers: fabric-ctl
    collapses the rows by host."""
    cpus = (os.cpu_count() or 0) if cpus is None else cpus

    def sh(args: list[str]) -> str | None:
        try:
            return run(args, capture_output=True, text=True, errors="replace", timeout=CMD_TIMEOUT_S, check=True,
                       stdin=subprocess.DEVNULL).stdout
        except (subprocess.SubprocessError, OSError):
            return None

    out: dict[str, Any] = {"status": "ok", "cpus": cpus, "loadavg": None, "mem_mb": None, "balloon_mb": None,
                           "disk": [], "leases": [], "top_rss": []}
    la = _read(os.path.join(proc, "loadavg"))
    if la:
        out["loadavg"] = [_num(x) for x in la.split()[:3]]
    mi = _read(os.path.join(proc, "meminfo"))
    if mi:
        kb = {m.group(1): int(m.group(2)) for m in re.finditer(r"^(\w+):\s+(\d+) kB", mi, re.M | re.A)}
        out["mem_mb"] = {"total": _mb(kb.get("MemTotal")), "available": _mb(kb.get("MemAvailable")),
                         "swap_total": _mb(kb.get("SwapTotal")), "swap_free": _mb(kb.get("SwapFree"))}
    xm = os.path.join(sys, "devices", "system", "xen_memory", "xen_memory0")
    cur, tgt = _read(os.path.join(xm, "info", "current_kb")), _read(os.path.join(xm, "target_kb"))
    if cur is not None or tgt is not None:
        smax = sh(["xenstore-read", "memory/static-max"])
        # static-max is xenstore's, and /dev/xen/xenbus is root:qubes on this
        # deployment: an account's daemon reads null, the operator's the number;
        # fabric-ctl prefers the row that has it. A half-present sysfs is null
        # per field, never 0 (Number(null) is 0).
        out["balloon_mb"] = {"current": None if cur is None else _mb(js.number(cur)),
                             "target": None if tgt is None else _mb(js.number(tgt)),
                             "static_max": _mb(js.number(smax.strip())) if smax else None}
    mounts = _read(os.path.join(proc, "mounts"))
    if mounts:
        seen: set[str] = set()
        for line in mounts.split("\n"):
            parts = line.split(" ")
            dev, mnt = parts[0], parts[1] if len(parts) > 1 else None
            if not dev.startswith("/dev/") or dev in seen or mnt is None:
                continue
            seen.add(dev)
            try:
                st = statfs(mnt.replace("\\040", " "))
            except OSError:
                continue   # a mount that vanished between the read and the statfs: not a row
            size, avail = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
            out["disk"].append({"mount": mnt, "size_gb": util.js_round(size / 2 ** 30), "avail_gb": util.js_round(avail / 2 ** 30),
                                "use_pct": util.js_round(100 * (size - avail) / size) if size else None})
    out["leases"] = _leases(leases, run)
    ps = sh(["ps", "-eo", "user:32,pid,rss,comm", "--sort=-rss"])
    if ps:
        rows = []
        for ln in ps.strip().split("\n")[1:7]:
            user, pid, rss, *comm = ln.split()
            rows.append({"user": user, "pid": int(pid), "rss_mb": _mb(int(rss)), "comm": " ".join(comm)})
        out["top_rss"] = rows
    return out


def _num(x: str) -> float | None:
    n = js.number(x)
    return None if n != n else n


def _leases(leases: str, run: Callable[..., Any]) -> list[dict]:
    # Only what fabric-lease itself can create is a lease: its name grammar,
    # [A-Za-z0-9][A-Za-z0-9._-]{0,63}. The directory is world-writable, so any
    # login can drop any name there; a name outside the grammar is not a lease
    # and never reaches the probe — and the name reaches only os.open,
    # never a command line; the grammar is the first gate, not the only one.
    try:
        names = sorted(n for n in os.listdir(leases) if LEASE_NAME.fullmatch(n))
    except OSError:
        return []   # no lease directory: no leases
    rows = []
    for n in names:
        f = os.path.join(leases, n)
        # The file is opened READ-ONLY here and the descriptor handed to
        # flock(1) — no shell, no command text built from a name in a
        # world-writable directory. The flock command opening the path itself
        # would use O_CREAT, which fs.protected_regular refuses on another
        # login's file in the sticky directory. O_NONBLOCK and O_NOFOLLOW, then
        # fstat on the descriptor rather than stat before the open: any login
        # can rename a fifo or a symlink over its own grammar-named entry in
        # between, and a blocking open of a reader-less fifo would hang this
        # op — and the daemon with it — for good. A SHARED lock,
        # not exclusive: an exclusive probe would hold a free lease for a
        # moment, and sixteen daemons probing at once could refuse a real
        # caller and each report the other's hold as a stale holder; a shared
        # probe is refused only by a real holder's exclusive lock (exit 1). A
        # file that cannot be opened (a hand-made 0600) is not a lease row.
        try:
            fd = os.open(f, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        except OSError:
            continue
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                continue
            try:
                held = run(["flock", "-s", "-n", str(fd)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=CMD_TIMEOUT_S, pass_fds=(fd,)).returncode == 1
            except (subprocess.SubprocessError, OSError):
                held = False
            if not held:
                continue
            # The record is the holder's own line — informational, and read
            # bounded: the first 256 bytes, never a whole file a login has grown.
            rec = os.pread(fd, 256, 0).decode("utf-8", "replace").split("\n")[0]
            fields = rec.split(" ")
            login, pid, since = (fields + ["", "", ""])[:3]
            # The job the holder named with --label: "<name> (<job>)" at the end.
            label = LEASE_LABEL.search(rec)
            n_pid = js.number(pid)
            rows.append({"name": n, "holder": login or None, "pid": int(n_pid) if math.isfinite(n_pid) and n_pid != 0 else None,
                         "since": since or None, "label": label.group(1) if label else None})
        finally:
            os.close(fd)
    return rows


# The account's own home, measured: what /home's space is spent on, and by
# whom (2026-10-04: /home on a host reached 90% and no account could say
# whose homes held it; the owner ran sudo du by hand). Each daemon
# measures its OWN home and nothing else: its largest top-level entries
# and every target/ directory under ~/projects to depth 3 — names and
# sizes only, never contents. One scan: du -xsk over the top-level entries
# but projects/, and du -xk -d 3 over projects/, whose own line is its
# total and whose target/ lines are the build directories (a target/
# inside a target/ is not counted twice). The total is the sum of the
# entries. du runs through the injected run, bounded: one that stops at
# its bound or reads part of a tree (exit 1 on an unreadable file) still
# reports what it measured, the status says partial and `errors` says
# why; a home that cannot be listed is failed, never a crash. Sizes in
# KiB, du's own unit. du's records end in NUL (-0), never a newline: a
# file name may hold one, and split on lines it invented entries, totals
# and target/ paths; a record whose path is not under the home is dropped
# (review of #92, round 4).
DISK_TIMEOUT_MS = 150000

DISK_MAX_BUFFER = 64 * 1024 * 1024

DISK_TOP = 5


def disk(home: str | None = None, run: Callable[..., Any] = util.run_bounded, timeout_ms: int = DISK_TIMEOUT_MS,
         readdir: Callable[[str], list[str]] = os.listdir) -> dict:
    home = os.path.expanduser("~") if home is None else home
    try:
        names = sorted(readdir(home))
    except OSError as e:
        return {"status": "failed", "error": f"{home} could not be listed ({errno.errorcode.get(e.errno or 0, str(e))})"}
    errors: list[str] = []

    def du(args: list[str], what: str) -> dict[str, int]:
        text, said = "", ""
        # LC_ALL=C: du's complaints are read below, so they must not be translated.
        try:
            r = run(["du", *args], timeout=timeout_ms / 1000, max_bytes=DISK_MAX_BUFFER, env={**os.environ, "LC_ALL": "C"})
            text, said = util.decode(r.stdout), util.decode(r.stderr)
        except (subprocess.SubprocessError, OSError) as e:
            text, said = util.decode(getattr(e, "output", None)), util.decode(getattr(e, "stderr", None))
            if isinstance(e, util.OutputOverflow):
                why = f"du's output passed its {DISK_MAX_BUFFER // 1048576} MiB bound"
            elif isinstance(e, subprocess.TimeoutExpired):
                why = f"du stopped at its {timeout_ms // 1000} s bound"
            elif isinstance(e, subprocess.CalledProcessError):
                why = f"du exit {e.returncode}"
            else:
                why = f"du exit {errno.errorcode.get(getattr(e, 'errno', 0) or 0, '?')}"
            errors.append(f"{what}: {why}{', partial' if text.strip() else ''}")
        # What du could not read is not in the total: say how much, and where to
        # look first. A rootless podman's volumes are owned by a sub-UID, so a
        # home that runs containers has some.
        unread = [m.group(1) for ln in said.split("\n") if (m := re.match(r"^du: cannot (?:read directory|access) (.*): [^:]*$", ln))]
        if unread:
            errors.append(f"{what}: {len(unread)} path{'' if len(unread) == 1 else 's'} du could not read, not counted; the first: {unread[0]}")
        sizes: dict[str, int] = {}
        outside: list[str] = []
        prefix = home if home.endswith(os.sep) else home + os.sep
        # Each record ends in NUL (-0): a newline is part of a name, never a separator.
        for rec in text.split("\0"):
            m = re.fullmatch(r"([0-9]+)\t(.+)", rec, re.S)
            if not m:
                continue
            if m.group(2) == home or m.group(2).startswith(prefix):
                sizes[m.group(2)] = int(m.group(1))
            else:
                outside.append(m.group(2))
        if outside:
            errors.append(f"{what}: {len(outside)} record{'' if len(outside) == 1 else 's'} outside {home} dropped; the first: {outside[0]}")
        return sizes

    projects = os.path.join(home, "projects")
    others = [os.path.join(home, n) for n in names if n != "projects"]
    entries = du(["-0", "-xsk", "--", *others], "home entries") if others else {}
    tree = du(["-0", "-xk", "--max-depth=3", "--", projects], "projects") if "projects" in names else {}
    largest = [{"name": os.path.basename(p), "kb": kb} for p, kb in entries.items()]
    if projects in tree:
        largest.append({"name": "projects", "kb": tree[projects]})
    largest.sort(key=lambda e: -e["kb"])
    targets = [{"path": os.path.relpath(p, home), "kb": kb} for p, kb in tree.items()
               if os.path.basename(p) == "target" and "target" not in os.path.relpath(os.path.dirname(p), projects).split(os.sep)]
    targets.sort(key=lambda t: -t["kb"])
    out: dict[str, Any] = {"status": "partial" if errors else "ok", "home": home, "total_kb": sum(e["kb"] for e in largest),
                           "largest": largest[:DISK_TOP], "targets": targets, "targets_kb": sum(t["kb"] for t in targets)}
    if errors:
        out["errors"] = errors
    return out


