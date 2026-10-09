#!/usr/bin/env python3
"""fabric-plan (agent-fabric ADR-047): the plans as data, a step's state
derived from its job, and the coordinator-only rule. The state directory is
the test's own and the two job sources are faked at the one edge the module
reads them through (subprocess.run's shape); the module's rules — what a
step's state is, which refusal says what, what a plan holds — are the code
under test. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Callable

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import plan  # noqa: E402

CASES: list[tuple[str, Callable[[], None]]] = []
HOSTS = {"hosts": {}, "placement": {"dev-01": "host-a", "dev-02": "host-a"}}


class Failed(Exception):
    pass


def case(name: str) -> Callable:
    def add(fn: Callable[[], None]) -> Callable[[], None]:
        CASES.append((name, fn))
        return fn
    return add


def check(good: bool, detail: Any = "") -> None:
    if not good:
        raise Failed(str(detail))


class world:
    """A state directory, a binding to `role`, a hosts registry placing dev-01 and dev-02."""
    def __init__(self, role: str | None = "fabric-coordinator"):
        self.role = role

    def __enter__(self) -> "world":
        self.dir = tempfile.mkdtemp(prefix="plan-test-")
        self.saved = {k: os.environ.get(k) for k in ("AGENT_FABRIC_STATE_DIR", "AGENT_FABRIC_HOSTS_REGISTRY")}
        os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(self.dir, "state")
        self.hosts = os.path.join(self.dir, "hosts.json")
        with open(self.hosts, "w", encoding="utf-8") as fh:
            json.dump(HOSTS, fh)
        os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = self.hosts
        if self.role:
            plan.identity.write_binding({"role": self.role})
        return self

    def __exit__(self, *exc: Any) -> None:
        import shutil
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.dir, ignore_errors=True)

    def run(self, *argv: str, reader: Any = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = plan.main(list(argv), reader=reader or Reader())
        return rc, out.getvalue(), err.getvalue()

    def files(self) -> list[str]:
        return sorted(os.path.join(d, f)[len(self.dir):] for d, _, fs in os.walk(self.dir) for f in fs
                      if f.endswith(".json") and "plans" in d)


class Reader:
    """Open and closed job lists per login; a login in `down` raises Unreadable from that source."""
    def __init__(self, open_: dict | None = None, closed: dict | None = None, open_down: dict | None = None,
                 closed_down: dict | None = None):
        self.o, self.c = open_ or {}, closed or {}
        self.od, self.cd = open_down or {}, closed_down or {}
        self.asked: list[tuple[str, str]] = []

    def open_jobs(self, login: str) -> list[dict]:
        self.asked.append(("open", login))
        if login in self.od:
            raise plan.Unreadable(self.od[login])
        return self.o.get(login, [])

    def closed_jobs(self, login: str) -> list[dict]:
        self.asked.append(("closed", login))
        if login in self.cd:
            raise plan.Unreadable(self.cd[login])
        return self.c.get(login, [])


def job(i: int, state: str) -> dict:
    return {"id": f"j{i}", "state": state, "title": f"job {i}"}


def make(w: world, *steps: tuple[str, str, str, str]) -> None:
    """A plan p with steps (title, owner, after, link)."""
    check(w.run("new", "p", "A plan")[0] == 0)
    for title, owner, after, link in steps:
        rc, _, err = w.run("step", "add", "p", title, "--owner", owner, *(["--after", after] if after else []))
        check(rc == 0, err)
    for i, (_, _, _, link) in enumerate(steps, 1):
        if link:
            check(w.run("link", "p", f"s{i}", link)[0] == 0)


def states(w: world, reader: Any) -> dict[str, tuple[str, str | None]]:
    rc, out, err = w.run("show", "p", "--json", reader=reader)
    check(rc == 0, err)
    return {s["id"]: (s["state"], s.get("reason")) for s in json.loads(out)["steps"]}


# ── rule 3: a step's state ──────────────────────────────────────────

@case("a linked step is its job's state, whichever of the six it is")
def _():
    for state in plan.JOB_STATES:
        with world() as w:
            make(w, ("one", "dev-01", "", "dev-01:j4"))
            rows = {"dev-01": [job(4, state)]}
            got = states(w, Reader(open_=rows if state in ("queued", "active", "blocked", "delivered") else {},
                                   closed=rows if state in ("done", "dropped") else {}))
            check(got == {"s1": (state, None)}, (state, got))


@case("a step with no job is planned, or waiting while a step it depends on is not done")
def _():
    with world() as w:
        make(w, ("a", "dev-01", "", "dev-01:j1"), ("b", "dev-02", "s1", ""), ("c", "dev-02", "", ""), ("d", "dev-02", "s1,s2", ""))
        for first, second in (("queued", "waiting"), ("active", "waiting"), ("blocked", "waiting"), ("delivered", "waiting")):
            got = states(w, Reader(open_={"dev-01": [job(1, first)]}))
            check(got["s2"] == (second, "waits for s1") and got["s3"] == ("planned", None), (first, got))
            check(got["s4"] == ("waiting", "waits for s1, s2"), got)
        got = states(w, Reader(closed={"dev-01": [job(1, "done")]}))
        check(got["s1"][0] == "done" and got["s2"] == ("planned", None) and got["s4"] == ("waiting", "waits for s2"), got)
        got = states(w, Reader(closed={"dev-01": [job(1, "dropped")]}))
        check(got["s2"][0] == "waiting", "a dropped dependency is not done")


@case("a job that cannot be read is unknown with the reason, and so is one that is on no list")
def _():
    with world() as w:
        make(w, ("a", "dev-01", "", "dev-01:j1"), ("b", "dev-02", "", "dev-02:j2"), ("c", "dev-02", "s1", ""))
        got = states(w, Reader(open_down={"dev-01": "fabric-ctl dev-01 jobs exited 2"}, closed_down={"dev-01": "host down"},
                               open_={"dev-02": [job(9, "active")]}))
        check(got["s1"][0] == "unknown" and "open list: fabric-ctl dev-01 jobs exited 2" in got["s1"][1]
              and "closed list: host down" in got["s1"][1], got)
        check(got["s2"] == ("unknown", "j2 is on neither the open nor the closed list of dev-02"), got)
        check(got["s3"][0] == "waiting", "a step behind an unknown one waits: unknown is not done")
        got = states(w, Reader(open_={"dev-01": [job(1, "active")], "dev-02": []}, closed_down={"dev-02": "host down"}))
        check(got["s1"] == ("active", None) and got["s2"][0] == "unknown" and "host down" in got["s2"][1], got)


@case("an open list that cannot be asked falls back to the closed list, which holds every job")
def _():
    with world() as w:
        make(w, ("a", "dev-01", "", "dev-01:j1"))
        got = states(w, Reader(open_down={"dev-01": "control agent down"}, closed={"dev-01": [job(1, "active")]}))
        check(got == {"s1": ("active", None)}, got)


@case("a state this tool does not know, and a malformed link, are unknown, not guessed")
def _():
    with world() as w:
        make(w, ("a", "dev-01", "", "dev-01:j1"))
        got = states(w, Reader(open_={"dev-01": [{"id": "j1", "state": "paused"}]}))
        check(got["s1"][0] == "unknown" and "'paused'" in got["s1"][1], got)
        doc = plan.identity.read_plan("p")
        doc["steps"][0]["job"] = "dev-01/j1"
        plan.identity.update_plan("p", lambda _d: doc)
        got = states(w, Reader())
        check(got["s1"][0] == "unknown" and "not <login>:<job-id>" in got["s1"][1], got)


@case("each login is asked once however many of its jobs a plan links")
def _():
    with world() as w:
        make(w, ("a", "dev-01", "", "dev-01:j1"), ("b", "dev-01", "", "dev-01:j2"), ("c", "dev-01", "", "dev-01:j3"))
        r = Reader(open_={"dev-01": [job(1, "active"), job(2, "queued")]}, closed={"dev-01": [job(3, "done")]})
        got = states(w, r)
        check([v[0] for v in got.values()] == ["active", "queued", "done"] and r.asked == [("open", "dev-01"), ("closed", "dev-01")], (got, r.asked))


# ── rule 2: the coordinator only ───────────────────────────────────

@case("any session not bound to fabric-coordinator is refused, every command, and writes nothing")
def _():
    for role in ("python-dev", None):
        with world(role) as w:
            for argv in (("new", "p", "t"), ("show",), ("show", "p"), ("export", "p"), ("step", "add", "p", "t", "--owner", "dev-01"),
                         ("link", "p", "s1", "dev-01:j1")):
                rc, out, err = w.run(*argv)
                check(rc == 1 and out == "" and f"kept by the role fabric-coordinator; this session is bound to {role or 'no role'}" in err
                      and err.count("\n") == 1, (role, argv, rc, out, err))
            check(w.files() == [], w.files())
    with world() as w:
        check(w.run("new", "p", "t")[0] == 0 and len(w.files()) == 1, "the control: the coordinator may")


# ── the commands ───────────────────────────────────────────────────

@case("new keeps a plan; the same id twice, and an id that names a path, are refused")
def _():
    with world() as w:
        rc, out, err = w.run("new", "wave-8", "  Wave 8,\n a plan ")
        d = plan.identity.read_plan("wave-8")
        check(rc == 0 and out == "plan wave-8\n" and d["title"] == "Wave 8, a plan" and d["status"] == "open" and d["steps"] == []
              and d["id"] == "wave-8" and d["created_at"], (rc, out, err, d))
        rc, _, err = w.run("new", "wave-8", "again")
        check(rc == 1 and err == "fabric-plan: plan wave-8 exists\n" and plan.identity.read_plan("wave-8")["title"] == "Wave 8, a plan", err)
        for bad in ("../x", "A", "a/b", "", "x" * 64, ".hidden"):
            rc, _, err = w.run("new", bad, "t")
            check(rc == 1 and "is not a plan id" in err, (bad, rc, err))
        for title in ("", "x" * 201, "bell\x07"):
            rc, _, err = w.run("new", "t1", title)
            check(rc == 1 and err.count("\n") == 1, (title, rc, err))
        check(len(w.files()) == 1, w.files())


@case("step add numbers the steps, keeps the order, checks the owner, the dependencies and the estimate")
def _():
    with world() as w:
        w.run("new", "p", "t")
        rc, out, _ = w.run("step", "add", "p", "first", "--owner", "dev-01", "--est-days", "2", "--note", "n")
        check(rc == 0 and out == "step s1\n")
        rc, out, _ = w.run("step", "add", "p", "second", "--owner", "dev-02", "--after", "s1,s1", "--est-days", "1.5")
        check(rc == 0 and out == "step s2\n")
        steps = plan.identity.read_plan("p")["steps"]
        check(steps[0] == {"id": "s1", "title": "first", "owner": "dev-01", "depends_on": [], "job": None, "est_days": 2, "note": "n"}
              and steps[1] == {"id": "s2", "title": "second", "owner": "dev-02", "depends_on": ["s1"], "job": None, "est_days": 1.5}, steps)
        for argv, why in ((("step", "add", "p", "t", "--owner", "nobody"), "placed on no host"),
                          (("step", "add", "p", "t", "--owner", "Bad Login"), "is not a login"),
                          (("step", "add", "p", "t", "--owner", "dev-01", "--after", "s9"), "not a step of p"),
                          (("step", "add", "p", "t", "--owner", "dev-01", "--est-days", "0"), "more than 0"),
                          (("step", "add", "p", "t", "--owner", "dev-01", "--est-days", "x"), "number of days"),
                          (("step", "add", "p", "t", "--owner", "dev-01", "--est-days", "99999"), "at most"),
                          (("step", "add", "nope", "t", "--owner", "dev-01"), "no plan 'nope'")):
            rc, _, err = w.run(*argv)
            check(rc == 1 and why in err and err.count("\n") == 1, (argv, rc, err))
        check(len(plan.identity.read_plan("p")["steps"]) == 2, "a refused step wrote nothing")


@case("an owner is refused when the hosts registry cannot be read: cannot tell is not placed")
def _():
    with world() as w:
        w.run("new", "p", "t")
        os.remove(w.hosts)
        rc, _, err = w.run("step", "add", "p", "t", "--owner", "dev-01")
        check(rc == 1 and "hosts registry could not be read (FileNotFoundError)" in err, err)


@case("link ties a step to <login>:<job>; another link needs --replace; a bad one is refused")
def _():
    with world() as w:
        make(w, ("a", "dev-01", "", ""))
        check(w.run("link", "p", "s1", "dev-02:j7")[0:2] == (0, "s1 -> dev-02:j7\n"))
        check(plan.identity.read_plan("p")["steps"][0]["job"] == "dev-02:j7")
        check(w.run("link", "p", "s1", "dev-02:j7")[0] == 0, "the same link again")
        rc, _, err = w.run("link", "p", "s1", "dev-01:j8")
        check(rc == 1 and "linked to dev-02:j7; --replace" in err and plan.identity.read_plan("p")["steps"][0]["job"] == "dev-02:j7", err)
        check(w.run("link", "p", "s1", "dev-01:j8", "--replace")[0] == 0 and plan.identity.read_plan("p")["steps"][0]["job"] == "dev-01:j8")
        for argv, why in ((("link", "p", "s1", "dev-01"), "not <login>:<job-id>"), (("link", "p", "s1", "dev-01:8"), "not <login>:<job-id>"),
                          (("link", "p", "s1", "nobody:j1"), "placed on no host"), (("link", "p", "s9", "dev-01:j1"), "no step s9"),
                          (("link", "x", "s1", "dev-01:j1"), "no plan 'x'")):
            rc, _, err = w.run(*argv)
            check(rc == 1 and why in err, (argv, err))


@case("show lists the plans, or one plan with its states; --json is one document")
def _():
    with world() as w:
        check(w.run("show")[1] == "no plans\n")
        make(w, ("port ops", "dev-01", "", "dev-01:j4"), ("review", "dev-02", "s1", ""))
        w.run("new", "q", "other")
        rc, out, _ = w.run("show")
        check(rc == 0 and out.splitlines()[0].startswith("p ") and "2 steps  A plan" in out.splitlines()[0]
              and out.splitlines()[1].startswith("q ") and "0 steps" in out, out)
        rc, out, _ = w.run("show", "p", reader=Reader(open_={"dev-01": [job(4, "active")]}))
        lines = out.splitlines()
        check(lines[0] == "plan p  [open]  A plan" and "active" in lines[1] and "dev-01 -> dev-01:j4" in lines[1]
              and "waiting" in lines[2] and "(waits for s1)" in lines[2], out)
        rc, out, _ = w.run("show", "--json")
        check([p["id"] for p in json.loads(out)["plans"]] == ["p", "q"] and json.loads(out)["plans"][0]["steps"] == 2, out)
        rc, out, _ = w.run("show", "p", "--json", reader=Reader(open_={"dev-01": [job(4, "active")]}))
        d = json.loads(out)
        check(d["id"] == "p" and d["read_at"] and d["steps"][0]["state"] == "active" and d["steps"][1]["state"] == "waiting", d)
        rc, _, err = w.run("show", "nope")
        check(rc == 1 and "no plan 'nope'" in err, err)


@case("export is markdown: a table of the steps with their states, and the notes")
def _():
    with world() as w:
        make(w, ("port | ops", "dev-01", "", "dev-01:j4"), ("review", "dev-02", "s1", ""))
        w.run("step", "add", "p", "third", "--owner", "dev-02", "--est-days", "3", "--note", "after review")
        rc, out, _ = w.run("export", "p", reader=Reader(open_={"dev-01": [job(4, "done")]}, closed={}))
        check(rc == 0 and out.startswith("# Plan p: A plan\n") and "| s1 | port \\| ops | dev-01 | dev-01:j4 |  |  | done |" in out
              and "| s2 | review | dev-02 |  | s1 |  | planned |" in out and "| s3 | third | dev-02 |  |  | 3 | planned |" in out
              and "Notes:\n- s3: after review" in out, out)


@case("the plan store: 0700 directory, 0600 files, an unmade plan is refused and leaves no file")
def _():
    with world() as w:
        w.run("new", "p", "t")
        d = plan.identity.plans_dir()
        check(oct(os.stat(d).st_mode & 0o777) == "0o700" and oct(os.stat(os.path.join(d, "p.json")).st_mode & 0o777) == "0o600",
              (oct(os.stat(d).st_mode), oct(os.stat(os.path.join(d, "p.json")).st_mode)))
        try:
            plan.identity.update_plan("never", lambda doc: None)
        except SystemExit as e:
            check("never" in str(e.code), e.code)
        else:
            check(False, "no refusal for a plan nothing made")
        check(not os.path.exists(os.path.join(d, "never.json")), "a null document was written")
        check(plan.identity.list_plans()[0]["id"] == "p" and len(plan.identity.list_plans()) == 1)
        for bad in ("../x", "A", "a/b", ""):
            try:
                plan.identity.plan_path(bad)
            except SystemExit:
                continue
            check(False, f"{bad!r} named a path")


@case("a human login is never a step's owner or link, and its account is never entered")
def _():
    with world() as w:
        with open(w.hosts, "w", encoding="utf-8") as fh:
            json.dump({**HOSTS, "placement": {**HOSTS["placement"], "me": "host-a"}, "kinds": {"me": "human"}}, fh)
        w.run("new", "p", "t")
        rc, _, err = w.run("step", "add", "p", "t", "--owner", "me")
        check(rc == 1 and "human login" in err and len(plan.identity.read_plan("p")["steps"]) == 0, err)
        w.run("step", "add", "p", "t", "--owner", "dev-01")
        rc, _, err = w.run("link", "p", "s1", "me:j1")
        check(rc == 1 and "human login" in err and plan.identity.read_plan("p")["steps"][0]["job"] is None, err)
        run = Run()
        try:
            plan.FleetReader(run=run).closed_jobs("me")
        except plan.Unreadable as e:
            check("human login" in str(e) and run.calls == [], (str(e), run.calls))
        else:
            check(False, "a human's closed list was asked")
        check(w.run("link", "p", "s1", "dev-02:j1")[0] == 0, "the control: an agent links")


@case("a hosts registry whose placement or kinds is not an object refuses: no traceback, no guess")
def _():
    with world() as w:
        w.run("new", "p", "t")
        for bad in ({"placement": {"dev-01": "host-a"}, "kinds": ["dev-01"]}, {"placement": ["dev-01"]}, ["x"]):
            with open(w.hosts, "w", encoding="utf-8") as fh:
                json.dump(bad, fh)
            rc, _, err = w.run("step", "add", "p", "t", "--owner", "dev-01")
            check(rc == 1 and "hosts registry could not be read (ValueError)" in err, (bad, rc, err))
            try:
                plan.FleetReader(run=Run()).closed_jobs("dev-01")
            except plan.Unreadable as e:
                check("hosts registry could not be read (ValueError)" in str(e), str(e))
            else:
                check(False, f"no refusal for {bad!r}")


@case("text from other accounts is shown, never obeyed: a reason and an export cell carry no control character")
def _():
    with world() as w:
        make(w, ("a", "dev-01", "", "dev-01:j1"))
        evil = "boom\x1b]0;owned\x07\n| x | y |\x9b31m"
        rc, out, _ = w.run("show", "p", reader=Reader(open_down={"dev-01": evil}, closed_down={"dev-01": evil}))
        check(rc == 0 and all(ord(c) >= 32 and not 127 <= ord(c) < 160 for c in out.replace("\n", "")) and out.count("\n") == 2, repr(out))
        rc, out, _ = w.run("export", "p", reader=Reader(open_down={"dev-01": evil}, closed_down={"dev-01": evil}))
        rows = [l for l in out.splitlines() if l.startswith("| s1 ")]
        check(rc == 0 and len(rows) == 1 and not any(c in out for c in "\x1b\x07\x9b"), repr(out))


# ── the readers behind the module ───────────────────────────────────

class Run:
    def __init__(self, *answers: Any):
        self.answers, self.calls = list(answers), []

    def __call__(self, argv: list[str], **kw: Any) -> Any:
        self.calls.append([os.path.basename(argv[0]), *argv[1:]])
        check(kw.get("timeout") == plan.CALL_TIMEOUT_S, "a bounded call")
        a = self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        out, rc = a if isinstance(a, tuple) else (a, 0)
        return subprocess.CompletedProcess(argv, rc, out, "stderr text" if rc else "")


def ctl_row(status: str = "ok", jobs: Any = None) -> str:
    return json.dumps({"account": "h/dev-01", "status": status, "jobs": jobs}) + "\n"


@case("FleetReader: fabric-ctl's row, the host executor's list, and what each failure says")
def _():
    run = Run(ctl_row("ok", {"status": "ok", "jobs": [job(1, "active")]}))
    r = plan.FleetReader(run=run)
    check(r.open_jobs("dev-01") == [job(1, "active")]
          and run.calls == [["fabric-ctl", "dev-01", "jobs", "--json", "--timeout", "20"]], run.calls)
    for answer, why in ((ctl_row("offline"), "control agent: offline"),
                        (ctl_row("ok", {"status": "error", "error": "no lock"}), "jobs: error (no lock)"),
                        (ctl_row("ok", {"status": "ok", "jobs": "x"}), "answered something else"),
                        ("not json\n", "answered something else"), ("", "answered something else"),
                        (("", 2), "exited 2: stderr text"),
                        ((ctl_row("no answer"), 1), "control agent: no answer"),
                        ((ctl_row("ok", {"status": "ok", "jobs": []}), 1), "exited 1"),
                        ((ctl_row("ok", {"status": "error", "error": "bad\x1b]0;x\x07\nline"}), 0), "(bad?]0;x??line)"),
                        (subprocess.TimeoutExpired("c", 60), "did not answer in 60 s"),
                        (FileNotFoundError(2, "No such file or directory"), "could not run: No such file or directory")):
        try:
            plan.FleetReader(run=Run(answer)).open_jobs("dev-01")
        except plan.Unreadable as e:
            check(why in str(e), (answer, str(e)))
        else:
            check(False, f"no refusal for {answer!r}")
    with world() as w:
        run = Run(json.dumps([job(5, "done")]))
        check(plan.FleetReader(run=run).closed_jobs("dev-01") == [job(5, "done")]
              and run.calls == [["fabric-host", "host-a", "run", "--as", "dev-01", "--", "fabric-jobs", "list", "--all", "--json"]], run.calls)
        for answer, why in (("{}", "answered something else"), ("x", "answered something else"), (("", 3), "exited 3")):
            try:
                plan.FleetReader(run=Run(answer)).closed_jobs("dev-01")
            except plan.Unreadable as e:
                check(why in str(e), (answer, str(e)))
            else:
                check(False, f"no refusal for {answer!r}")
        try:
            plan.FleetReader(run=Run()).closed_jobs("nobody")
        except plan.Unreadable as e:
            check("placed on no host" in str(e), str(e))
        os.remove(w.hosts)
        try:
            plan.FleetReader(run=Run()).closed_jobs("dev-01")
        except plan.Unreadable as e:
            check("hosts registry could not be read" in str(e), str(e))


@case("the default runner is the process-group killer: a timeout leaves no grandchild running")
def _():
    check(plan.FleetReader().run is plan.bounded_run)
    import time
    with tempfile.TemporaryDirectory() as tmp:
        pidfile = os.path.join(tmp, "pid")
        try:
            plan.bounded_run(["sh", "-c", f"sleep 30 & echo $! > {pidfile}; wait"], timeout=1)
        except subprocess.TimeoutExpired:
            pass
        else:
            check(False, "no timeout")
        pid = int(open(pidfile, encoding="utf-8").read())

        def alive() -> bool:
            # A killed process nobody reaps (a container's init does not) stays a zombie, and kill(pid, 0) still finds it.
            try:
                with open(f"/proc/{pid}/stat") as fh:
                    return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
            except (FileNotFoundError, ProcessLookupError):   # the second: a /proc entry caught mid-exit
                return False
        for _ in range(50):
            if not alive():
                return
            time.sleep(0.1)
        check(False, "the grandchild outlived the timeout")


def main() -> int:
    fails = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok   {name}")
        except Failed as e:
            fails += 1
            print(f"  FAIL {name}: {e}")
    print(f"\n{'FAILED' if fails else 'all passed'}: {len(CASES) - fails}/{len(CASES)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
