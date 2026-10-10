#!/usr/bin/env python3
"""tools/fabric/pause.py and bin/fabric-pause: which logins pass, which are
refused and why, that a refused login is never signalled, that a passed one is
read back until presence shows no session, and the fallback while no `pause`
operation exists. The control plane is a fake `run`: fixtures of fabric-ctl's
--json rows, as bin/fabric-ctl prints them. Plain script: prints ok/FAIL, exit 1
on any failure."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import pause  # noqa: E402


def job(jid: str, state: str, title: str = "work", blocked_on: str | None = None) -> dict:
    return {"id": jid, "state": state, "title": title, "blocked_on": blocked_on}


def jobs_row(login: str, jobs: list | None = None, status: str = "ok", op_status: str = "ok", error: str = "") -> dict:
    res: dict = {"status": op_status, "jobs": jobs if jobs is not None else []}
    if error:
        res["error"] = error
    return {"account": login, "host": "h", "status": status, "op": "jobs", "jobs": res if status == "ok" else None}


def presence_row(login: str, online: bool = True, planning: bool = False, project: str = "agent-fabric",
                 status: str = "ok", op_status: str = "ok") -> dict:
    res = {"status": op_status, "online": online, "sessions": 1 if online else 0, "planning": planning, "project": project}
    return {"account": login, "host": "h", "status": status, "op": "presence", "presence": res if status == "ok" else None}


class Fleet:
    """fabric-ctl, as a table: (target, op) -> rows; every call is recorded."""

    def __init__(self, rows: dict, *, stderr: str = "", rc: int = 0):
        self.rows, self.calls, self.stderr, self.rc = rows, [], stderr, rc

    def __call__(self, argv: list[str], timeout: float) -> subprocess.CompletedProcess:
        self.calls.append(list(argv))
        key = (argv[1], argv[2])
        rows = self.rows.get(key)
        if callable(rows):
            rows = rows()
        if rows is None:
            return subprocess.CompletedProcess(argv, 2, "", f"fabric-ctl: {argv[1]} is not an agent")
        return subprocess.CompletedProcess(argv, self.rc, "".join(json.dumps(r) + "\n" for r in rows), self.stderr)


def run_pause(argv: list[str], fleet: Fleet, signal=None) -> tuple[int, str, str, list[str]]:
    out, err, signalled = io.StringIO(), io.StringIO(), []

    def default_signal(login: str) -> int:
        signalled.append(login)
        return 1
    clock = iter(range(0, 10_000, 5))
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = pause.pause(argv, run=fleet, signal=signal or default_signal, sleep=lambda s: None, clock=lambda: next(clock))
    return rc, out.getvalue(), err.getvalue(), signalled


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail!r}"))
        fails += not good

    def one(login: str, jobs: list | None, **pres) -> Fleet:
        return Fleet({(login, "jobs"): [jobs_row(login, jobs)], (login, "presence"): [presence_row(login, **pres)]})

    print("the verdicts, --dry-run")
    f = one("a", [job("j1", "blocked", blocked_on="paused by the owner"), job("j2", "queued"), job("j3", "delivered")])
    rc, out, err, sig = run_pause(["a", "--dry-run"], f)
    check("blocked, queued and delivered jobs pass: pause, with the working-copy check said unchecked",
          rc == 0 and out.startswith("a") and " pause " in out and "working copies unchecked" in out, out)
    check("a dry run signals nothing and reads only jobs and presence",
          sig == [] and {c[2] for c in f.calls} == {"jobs", "presence"} and all("--json" in c for c in f.calls), f.calls)

    f = one("a", [job("j1", "active", "the thing"), job("j2", "active", "another")])
    rc, out, _, _ = run_pause(["a", "--dry-run"], f)
    check("an active job refuses, each named", rc == 1 and " refuse " in out and "active job j1: the thing" in out
          and "active job j2: another" in out, out)
    rc, out, _, _ = run_pause(["a", "--dry-run"], one("a", [], planning=True))
    check("a planning session refuses", rc == 1 and "a plan awaits approval" in out, out)
    rc, out, _, _ = run_pause(["a", "--dry-run"], one("a", [job("j1", "blocked", blocked_on="anything at all")]))
    check("no text is matched on the blocked reason", rc == 0 and " pause " in out, out)
    rc, out, _, _ = run_pause(["a", "--dry-run"], one("a", [], online=False))
    check("no session running: idle, nothing to signal", rc == 0 and " idle " in out and "no session running" in out, out)
    rc, out, _, _ = run_pause(["a", "--dry-run"], one("a", [job("j1", "active")], online=False))
    check("…but an active job still refuses a login with no session", rc == 1 and " refuse " in out, out)

    print("unknown stays unknown")
    cases = {
        "jobs silent": Fleet({("a", "jobs"): [{"account": "a", "host": "h", "status": "no answer"}], ("a", "presence"): [presence_row("a")]}),
        "jobs op failed": Fleet({("a", "jobs"): [jobs_row("a", op_status="failed", error="boom")], ("a", "presence"): [presence_row("a")]}),
        "jobs not a list": Fleet({("a", "jobs"): [{"account": "a", "host": "h", "status": "ok", "jobs": {"status": "ok", "jobs": None}}],
                                  ("a", "presence"): [presence_row("a")]}),
        "presence silent": Fleet({("a", "jobs"): [jobs_row("a")], ("a", "presence"): [{"account": "a", "host": "h", "status": "no answer"}]}),
        "presence op failed": Fleet({("a", "jobs"): [jobs_row("a")], ("a", "presence"): [presence_row("a", op_status="failed")]}),
        "no row for it": Fleet({("a", "jobs"): [jobs_row("zzz")], ("a", "presence"): [presence_row("a")]}),
    }
    for label, fl in cases.items():
        rc, out, _, sig = run_pause(["a"], fl)
        check(f"{label}: refused, never signalled", rc == 1 and " refuse " in out and sig == [] and "unreadable" in out, (rc, out, sig))
    rc, out, err, _ = run_pause(["nobody", "--dry-run"], Fleet({}))
    check("a login fabric-ctl refuses (not an agent) is refused with fabric-ctl's words",
          rc == 1 and " refuse " in out and "is not an agent" in out, (out, err))
    rc, out, err, _ = run_pause(["a"], Fleet({("a", "jobs"): lambda: (_ for _ in ()).throw(pause.PauseError("fabric-ctl did not answer within 45 s")),
                                              ("a", "presence"): [presence_row("a")]}))
    check("fabric-ctl hanging is a refusal that says so", rc == 1 and "did not answer within 45 s" in out, (out, err))

    print("targets")
    fleet = {("all", "presence"): [presence_row("a", project="p1"), presence_row("b", project="p2"),
                                    presence_row("c", project="p1", planning=True),
                                    {"account": "d", "host": "h", "status": "no answer"}],
             ("all", "jobs"): [jobs_row("a"), jobs_row("b"), jobs_row("c"), jobs_row("d")]}
    rc, out, _, _ = run_pause(["--project", "p1", "--dry-run"], Fleet(dict(fleet)))
    verdict = {ln.split()[0]: ln.split()[1] for ln in out.splitlines()}
    check("--project: its logins only, the planning one refused, a silent account refused (its project is unknown)",
          rc == 1 and verdict == {"a": "pause", "c": "refuse", "d": "refuse"}, out)
    rc, out, _, _ = run_pause(["--all", "--dry-run"], Fleet(dict(fleet)))
    check("--all: every placed agent, one row each", rc == 1 and len(out.splitlines()) == 4, out)
    f = Fleet(dict(fleet))
    run_pause(["--all", "--dry-run"], f)
    check("--all asks the fleet once per op, not once per login", [c[1] for c in f.calls] == ["all", "all", "all"], f.calls)
    rc, out, err, _ = run_pause(["--project", "nope", "--dry-run"], Fleet({("all", "presence"): [presence_row("a", project="p1")],
                                                                         ("all", "jobs"): [jobs_row("a")]}))
    check("a project nobody is in: said, exit 1", rc == 1 and "no login matches" in err, (out, err))

    print("usage")
    for argv in ([], ["--all", "a"], ["--project", "p", "--all"], ["--project"], ["--project", "--all"], ["Bad"], ["--nope", "a"], ["a/b"]):
        rc, out, err, sig = run_pause(argv, Fleet({}))
        check(f"{argv or 'no target'}: exit 2, usage on stderr, nothing asked", rc == 2 and "usage: fabric-pause" in err and out == "", (rc, err))
    rc, out, _, _ = run_pause(["--help"], Fleet({}))
    check("--help: the header, exit 0", rc == 0 and "fabric-pause: pause agents" in out, out)
    rc, out, err, _ = run_pause(["--all"], Fleet({("all", "presence"): []}, stderr="fabric-ctl: no relay", rc=3))
    check("fabric-ctl with no rows: its last line, exit 1", rc == 1 and "no relay" in err, (rc, err))

    print("without --dry-run")
    f = one("a", [job("j1", "blocked")])

    def unavailable(login: str) -> int:
        raise pause.Unavailable("the control agent has no pause operation yet")
    rc, out, err, _ = run_pause(["a"], f, signal=unavailable)
    check("no pause operation: nothing signalled, the passed logins listed for the operator, exit 2",
          rc == 2 and "nothing was signalled" in err and "operator" in err and " a" in err, (rc, out, err))
    fleet2 = Fleet({("all", "presence"): [presence_row("ok1"), presence_row("busy"), presence_row("ok2")],
                    ("all", "jobs"): [jobs_row("ok1"), jobs_row("busy", [job("j9", "active")]), jobs_row("ok2")]})
    seen: list[str] = []

    def killing(login: str) -> int:
        seen.append(login)
        online[login] = False
        return 1
    online = {"ok1": True, "ok2": True}

    def ctl(argv, timeout):
        if argv[1] in online and argv[2] == "presence":
            return subprocess.CompletedProcess(argv, 0, json.dumps(presence_row(argv[1], online=online[argv[1]])) + "\n", "")
        return fleet2(argv, timeout)
    out_b, err_b = io.StringIO(), io.StringIO()
    clock = iter(range(0, 10_000, 5))
    with contextlib.redirect_stdout(out_b), contextlib.redirect_stderr(err_b):
        rc = pause.pause(["--all"], run=ctl, signal=killing, sleep=lambda s: None, clock=lambda: next(clock))
    check("a refused login is never signalled; each passed one is signalled once", seen == ["ok1", "ok2"], seen)
    check("a passed login ends read back as paused, with presence showing no session",
          "ok1" in out_b.getvalue() and out_b.getvalue().count("paused") == 2 and "presence shows no session" in out_b.getvalue(), out_b.getvalue())
    check("the refusal still makes the run exit 1", rc == 1, rc)

    stuck = Fleet({("a", "jobs"): [jobs_row("a")], ("a", "presence"): [presence_row("a")]})
    rc, out, err, sig = run_pause(["a"], stuck)
    check("a login that stays up after the signal is reported still up, exit 1",
          rc == 1 and "still up" in out and "still has 1 session(s)" in out and sig == ["a"], (rc, out))
    blind = Fleet({("a", "jobs"): [jobs_row("a")]})
    calls = {"n": 0}

    def flaky_ctl(argv, timeout):
        if argv[2] == "presence":
            calls["n"] += 1
            if calls["n"] > 1:
                raise pause.PauseError("fabric-ctl did not answer within 45 s")
            return subprocess.CompletedProcess(argv, 0, json.dumps(presence_row("a")) + "\n", "")
        return blind(argv, timeout)
    out_c = io.StringIO()
    clock = iter(range(0, 10_000, 5))
    with contextlib.redirect_stdout(out_c), contextlib.redirect_stderr(io.StringIO()):
        rc = pause.pause(["a"], run=flaky_ctl, signal=lambda login: 1, sleep=lambda s: None, clock=lambda: next(clock))
    check("a read-back that cannot be read is not 'paused'", rc == 1 and "still up" in out_c.getvalue() and "did not answer" in out_c.getvalue(), out_c.getvalue())

    print("the real command")
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "AGENT_FABRIC_PYTHON": sys.executable}
    r = subprocess.run([os.path.join(HERE, "bin", "fabric-pause")], env=env, capture_output=True, text=True, timeout=60,
                       stdin=subprocess.DEVNULL)
    check("bin/fabric-pause with no target: usage, exit 2", r.returncode == 2 and "usage: fabric-pause" in r.stderr, (r.returncode, r.stderr))
    r = subprocess.run([os.path.join(HERE, "bin", "fabric-pause"), "--help"], env=env, capture_output=True, text=True, timeout=60,
                       stdin=subprocess.DEVNULL)
    check("bin/fabric-pause --help: exit 0, the module's header", r.returncode == 0 and "pause agents before a host restart" in r.stdout, r.stderr)
    r = subprocess.run([os.path.join(HERE, "bin", "fabric-pause"), "--all"], env={**env, "AGENT_FABRIC_PYTHON": "/nonexistent/python"},
                       capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    check("no pinned Python: exit 127 naming fabric-pause", r.returncode == 127 and r.stderr.startswith("fabric-pause: "), (r.returncode, r.stderr))

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
