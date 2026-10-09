#!/usr/bin/env python3
"""A REQUEST to a login becomes a queued job on its list (agent-fabric
ADR-037 §7): the inbox's half and the send's half, tools/fabric/gzcoord/
intake.py. The job list and the control plane are faked at the edge the
module calls them through; the module's own rules (which messages, once per
id, the title, who may ask, what a failure says) are the code under test.
Plain script: prints ok/FAIL, exit 1 on any failure."""
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gzcoord import gzmsg, inbox, intake, send  # noqa: E402
import test_gzcoord_protocol as P  # noqa: E402 — its relay stub, scratch workspace and command environment

ME = "host-a/dev-01"
MID = "01a11f64-ba5d-75f8-aa8d-4e755dc0f76e"
HOSTS = {"hosts": {"host-a": {"operator": "boss"}}}
CASES: list[tuple[str, Callable[[], None]]] = []


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


class Refused(Exception):
    pass


class FakeJobs:
    """What intake asks of jobs.py: mutate(fn) over a list, new_job(doc, title, project, source)."""
    def __init__(self, doc: dict | None = None, refuse: str | None = None):
        self.doc = doc if doc is not None else {"jobs": []}
        self.refuse = refuse

    def mutate(self, fn: Callable[[dict], Any]) -> Any:
        if self.refuse:
            raise Refused(self.refuse)
        return fn(self.doc)

    def new_job(self, doc: dict, title: str, *, project: Any = None, source: Any = None) -> dict:
        job = {"id": f"j{len(doc['jobs']) + 1}", "title": title, "project": project, "source": source}
        doc["jobs"].append(job)
        return job


def delivery(mtype: str = "REQUEST", mid: str = MID, mine: bool = True, **meta: Any) -> dict:
    metadata = {"FROM": "host-a/user", "TO": ME, "MESSAGE-ID": mid, "SUBJECT": "a subject", "PROJECT": "agent-fabric", **meta}
    metadata = {k: v for k, v in metadata.items() if v is not None}
    return {"rec": {"seq": 7, "sender": "host-a/user"}, "msg": {"type": mtype, "metadata": metadata}, "isMine": mine}


def receive(items: list[dict], jobs: FakeJobs) -> tuple[list[str], str]:
    err = io.StringIO()
    return intake.queue_received(items, {"address": ME}, jobs=jobs, err=err), err.getvalue()


@case("a REQUEST to this login is queued, once per MESSAGE-ID: a redelivery adds nothing")
def _():
    jobs = FakeJobs()
    lines, err = receive([delivery()], jobs)
    check(lines == [f"queued as j1: a subject (REQUEST {MID})"] and len(jobs.doc["jobs"]) == 1 and err == "", (lines, err))
    check(jobs.doc["jobs"][0]["source"] == {"kind": "request", "message_id": MID, "from": "host-a/user", "seq": 7}
          and jobs.doc["jobs"][0]["project"] == "agent-fabric", jobs.doc)
    lines, err = receive([delivery()], jobs)
    check(lines == [] and len(jobs.doc["jobs"]) == 1, (lines, jobs.doc))
    lines, _ = receive([delivery(), delivery()], FakeJobs())
    check(len(lines) == 1, lines)       # twice in one page is one job


@case("a job the sender's half wrote (the id in its title) is the job: nothing is added")
def _():
    jobs = FakeJobs({"jobs": [{"id": "j3", "title": f"a subject (REQUEST {MID})", "source": {"kind": "owner"}}]})
    lines, err = receive([delivery()], jobs)
    check(lines == [] and len(jobs.doc["jobs"]) == 1 and err == "", (lines, jobs.doc, err))
    lines, _ = receive([delivery(mid="01a11f64-0000-7000-8000-000000000001")], jobs)
    check(len(lines) == 1, lines)       # the control: another id is another job


@case("only a REQUEST whose TO is this login: not TO-ROLE, BROADCAST, another login, or another type")
def _():
    items = [delivery(TO=None, **{"TO-ROLE": "python-dev"}),
             delivery(TO=None, BROADCAST="true"),
             delivery(TO="host-a/dev-02"),
             delivery(mtype="REPLY"), delivery(mtype="INFO"), delivery(mtype="OBSERVATION"),
             delivery(mine=False)]
    jobs = FakeJobs()
    lines, err = receive(items, jobs)
    check(lines == [] and jobs.doc["jobs"] == [] and err == "", (lines, jobs.doc, err))
    lines, _ = receive([delivery()], FakeJobs())
    check(len(lines) == 1, "the control: a REQUEST to this login is queued")


@case("a list that cannot take the job is one stderr line; the delivery stands")
def _():
    lines, err = receive([delivery()], FakeJobs(refuse="no working copy of agent-fabric"))
    check(lines == [] and err == f"gzcoord: REQUEST {MID} was not queued on your job list: no working copy of agent-fabric\n", (lines, err))


@case("through the real job list: a REQUEST is one queued job with its source, and redelivery adds none")
def _():
    saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
    try:
        with tempfile.TemporaryDirectory() as state:
            os.environ["AGENT_FABRIC_STATE_DIR"] = state
            item, err = delivery(PROJECT=None), io.StringIO()
            lines = intake.queue_received([item], {"address": ME}, err=err)
            check(len(lines) == 1 and lines[0].startswith("queued as j1: a subject (REQUEST") and err.getvalue() == "", (lines, err.getvalue()))
            check(intake.queue_received([item], {"address": ME}, err=err) == [], "redelivered")
            found = [os.path.join(d, f) for d, _, fs in os.walk(state) for f in fs if f == "jobs.json"]
            check(len(found) == 1, found)
            with open(found[0], encoding="utf-8") as fh:
                doc = json.load(fh)
            check(len(doc["jobs"]) == 1 and doc["jobs"][0]["state"] == "queued" and doc["jobs"][0]["priority"] == "normal"
                  and doc["jobs"][0]["source"] == {"kind": "request", "message_id": MID, "from": "host-a/user", "seq": 7}, doc)
    finally:
        if saved is None:
            os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
        else:
            os.environ["AGENT_FABRIC_STATE_DIR"] = saved


@case("the inbox prints the delivery and, below it, what it queued")
def _():
    real = intake.queue_received
    try:
        intake.queue_received = lambda classified, me, **kw: ["queued as j9: a subject"]
        check(inbox.with_queued("the delivery", [], {}) == "the delivery\nqueued as j9: a subject")
        intake.queue_received = lambda classified, me, **kw: []
        check(inbox.with_queued("the delivery", [], {}) == "the delivery")
    finally:
        intake.queue_received = real


class FakeCtl:
    """fabric-ctl: the first call is the list check (`jobs --json`), the next the add. `listing` is
    what the check prints; `stdout`/`returncode`/`stderr`/`raises` answer the add."""
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "", raises: BaseException | None = None,
                 listing: str = ""):
        self.calls: list[list[str]] = []
        self.listing = listing
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        self.raises = raises

    def __call__(self, argv: list[str], **kw: Any) -> Any:
        self.calls.append(argv)
        if argv[2] == "jobs":
            return subprocess.CompletedProcess(argv, 0, self.listing, "")
        if self.raises:
            raise self.raises
        return self.result

    def adds(self) -> list[list[str]]:
        return [c for c in self.calls if c[2] == "jobs-add"]


def sent(ctl: FakeCtl, sender: str = "boss", **over: Any) -> tuple[str | None, str]:
    msg = {"type": "REQUEST", "metadata": {"TO": ME, "MESSAGE-ID": MID, "SUBJECT": "a subject", "PROJECT": "agent-fabric", **over}}
    err = io.StringIO()
    return intake.queue_for_addressee(msg, sender=sender, hosts=HOSTS, run=ctl, err=err), err.getvalue()


@case("the host's operator asks the addressee's control agent for the job, the id in its title")
def _():
    ctl = FakeCtl("dev-01   added  j9\n")
    job, err = sent(ctl)
    check(job == "j9" and err == "", (job, err))
    check(ctl.calls == [[intake.CTL, "dev-01", "jobs", "--json"],
                        [intake.CTL, "dev-01", "jobs-add", "--project", "agent-fabric", "--", f"a subject (REQUEST {MID})"]], ctl.calls)


@case("a long SUBJECT is cut to jobs-add's limit and the id is kept")
def _():
    ctl = FakeCtl("dev-01 added j2")
    sent(ctl, SUBJECT="x" * 900)
    title = ctl.adds()[0][-1]
    check(len(title) == intake.TITLE_MAX and title.endswith(f" (REQUEST {MID})"), (len(title), title[-60:]))
    check(intake.title_for("  two\twords \n", MID) == f"two words (REQUEST {MID})")


@case("anyone but the host's operator asks nothing; so for TO-ROLE, BROADCAST and other types")
def _():
    ctl = FakeCtl("dev-01 added j9")
    check(sent(ctl, sender="dev-02") == (None, "") and ctl.calls == [])
    msg = {"type": "REQUEST", "metadata": {"TO-ROLE": "python-dev", "MESSAGE-ID": MID, "SUBJECT": "s"}}
    check(intake.queue_for_addressee(msg, sender="boss", hosts=HOSTS, run=ctl) is None and ctl.calls == [])
    msg = {"type": "INFO", "metadata": {"TO": ME, "MESSAGE-ID": MID, "SUBJECT": "s"}}
    check(intake.queue_for_addressee(msg, sender="boss", hosts=HOSTS, run=ctl) is None and ctl.calls == [])
    msg = {"type": "REQUEST", "metadata": {"TO": "host-b/dev-01", "MESSAGE-ID": MID, "SUBJECT": "s"}}
    check(intake.queue_for_addressee(msg, sender="boss", hosts=HOSTS, run=ctl) is None and ctl.calls == [],
          "host-b has no operator in the registry")
    check(sent(FakeCtl("dev-01 added j9"))[0] == "j9", "the control: the operator's REQUEST is asked")


@case("a control call that fails, times out, is missing or answers nothing usable: one line, no job")
def _():
    for ctl, said in ((FakeCtl("dev-01   refused  title is one line", 1), "title is one line"),
                      (FakeCtl("", 2, "fabric-ctl: no host"), "fabric-ctl: no host"),
                      (FakeCtl("dev-01 offline", 0), "dev-01 offline"),
                      (FakeCtl("dev-01 added j9", 1, "fabric-ctl: late failure"), "fabric-ctl: late failure"),
                      (FakeCtl(raises=subprocess.TimeoutExpired("c", 30)), "did not answer in 30 s"),
                      (FakeCtl(raises=FileNotFoundError(2, "No such file or directory")), "No such file or directory")):
        job, err = sent(ctl)
        check(job is None and err.count("\n") == 1 and said in err and MID in err, (said, job, err))


@case("send.queue_request: a hosts registry that cannot be read is said; the operator's REQUEST reaches the call")
def _():
    msg = {"type": "REQUEST", "metadata": {"TO": ME, "MESSAGE-ID": MID, "SUBJECT": "s"}}
    saved = os.environ.get("AGENT_FABRIC_HOSTS_REGISTRY")
    err, real = io.StringIO(), sys.stderr
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = os.path.join(tmp, "absent.json")
            sys.stderr = err
            send.queue_request(msg, {"agent": "boss"})
            check("hosts registry could not be read (FileNotFoundError)" in err.getvalue() and MID in err.getvalue(), err.getvalue())
            path = os.path.join(tmp, "hosts.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(HOSTS, fh)
            os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = path
            calls = []
            real_q = intake.queue_for_addressee
            intake.queue_for_addressee = lambda m, **kw: calls.append((m, kw["sender"], kw["hosts"])) or "j4"
            try:
                err.truncate(0)
                err.seek(0)
                send.queue_request(msg, {"agent": "boss"})
                send.queue_request({"type": "INFO", "metadata": {"TO": ME}}, {"agent": "boss"})
            finally:
                intake.queue_for_addressee = real_q
            check(len(calls) == 1 and calls[0][1:] == ("boss", HOSTS), calls)
            check(err.getvalue() == f"queued as j4 on {ME}'s job list\n", err.getvalue())
    finally:
        sys.stderr = real
        if saved is None:
            os.environ.pop("AGENT_FABRIC_HOSTS_REGISTRY", None)
        else:
            os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = saved


def listing_row(*titles: str) -> str:
    return json.dumps({"account": "host-a/dev-01", "status": "ok",
                       "jobs": {"status": "ok", "jobs": [{"id": f"j{i}", "state": "queued", "title": t} for i, t in enumerate(titles, 1)]}}) + "\n"


@case("the sender asks nothing when the addressee's list already shows the REQUEST (a live watch was first)")
def _():
    ctl = FakeCtl("dev-01 added j9", listing=listing_row("something else", f"a subject (REQUEST {MID})"))
    job, err = sent(ctl)
    check(job is None and err == "" and ctl.adds() == [] and len(ctl.calls) == 1, (job, err, ctl.calls))
    for listing, why in ((listing_row("something else"), "another title"), ("not json\n", "a list that cannot be read"),
                         ("", "an empty answer")):
        ctl = FakeCtl("dev-01 added j9", listing=listing)
        check(sent(ctl)[0] == "j9" and len(ctl.adds()) == 1, why)


@case("a REQUEST whose PROJECT has no working copy here is queued with that project and no working copy")
def _():
    saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
    try:
        with tempfile.TemporaryDirectory() as state:
            os.environ["AGENT_FABRIC_STATE_DIR"] = state
            err = io.StringIO()
            lines = intake.queue_received([delivery(PROJECT="no-such-project")], {"address": ME}, err=err)
            check(len(lines) == 1 and err.getvalue() == "", (lines, err.getvalue()))
            doc = json.load(open([os.path.join(d, f) for d, _, fs in os.walk(state) for f in fs if f == "jobs.json"][0], encoding="utf-8"))
            check(doc["jobs"][0]["project"] == "no-such-project" and doc["jobs"][0]["working_copy"] is None, doc["jobs"])
    finally:
        if saved is None:
            os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
        else:
            os.environ["AGENT_FABRIC_STATE_DIR"] = saved


@case("a MESSAGE-ID that is not an id is said and not queued; a short id is never found inside another title")
def _():
    jobs = FakeJobs({"jobs": [{"id": "j1", "title": "fix a bug", "source": {"kind": "self"}}]})
    for bad in ("a", "1", "01a11f64", "x" * 200):
        lines, err = receive([delivery(mid=bad)], jobs)
        check(lines == [] and err.count("\n") == 1 and "MESSAGE-ID is not an id" in err and len(jobs.doc["jobs"]) == 1, (bad, lines, err))
    check(not intake.listed(jobs.doc, "a") and not intake.listed(jobs.doc, MID))
    check(intake.listed({"jobs": [{"title": f"s (REQUEST {MID})"}]}, MID))


@case("whatever the sender's half raises is a line, never an exception: a registry of the wrong shape, undecodable output")
def _():
    check(intake.operator_of(ME, {"hosts": ["host-a"]}) is None and intake.operator_of(ME, []) is None
          and intake.operator_of(ME, {"hosts": {"host-a": "boss"}}) is None)
    bad = FakeCtl(raises=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"))
    job, err = sent(bad)
    check(job is None and err.count("\n") == 1 and MID in err, (job, err))
    msg = {"type": "REQUEST", "metadata": {"TO": ME, "MESSAGE-ID": MID, "SUBJECT": "s"}}
    out, real = io.StringIO(), sys.stderr
    saved = os.environ.get("AGENT_FABRIC_HOSTS_REGISTRY")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "hosts.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"hosts": ["a list"]}, fh)
            os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = path
            sys.stderr = out
            send.queue_request(msg, {"agent": "boss"})
    finally:
        sys.stderr = real
        if saved is None:
            os.environ.pop("AGENT_FABRIC_HOSTS_REGISTRY", None)
        else:
            os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = saved
    check(out.getvalue() == "", out.getvalue())     # no operator named: nothing asked, nothing said


class command_env:
    """The process environment of a command run in this process: cmd_env's scratch
    workspace (never the checkout's relay), a scratch state directory, no journal."""
    def __init__(self, **extra: str):
        self.extra = extra

    def __enter__(self) -> str:
        self.state = tempfile.mkdtemp(prefix="intake-state-")
        env = P.cmd_env(AGENT_FABRIC_STATE_DIR=self.state, GZCOORD_JOURNAL="off", GZCOORD_CHANNEL="fixture:chan",
                        CLAUDE_BRIDGE_AUTH_TOKEN="tok", **self.extra)
        for k in ("AGENT_FABRIC_OPERATOR", "AGENT_FABRIC_HOSTS_REGISTRY"):
            env.pop(k, None)
        env.update(self.extra)
        self.saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(env)
        return self.state

    def __exit__(self, *exc: Any) -> None:
        os.environ.clear()
        os.environ.update(self.saved)
        import shutil
        shutil.rmtree(self.state, ignore_errors=True)


def request_text(to: str, frm: str) -> str:
    return (f"[GZCOORD/1] REQUEST\nFROM: {frm}\nROLE: fabric-coordinator\nPROJECT: agent-fabric\nTO: {to}\nREPLY-EXPECTED: yes\n"
            f"MESSAGE-ID: {MID}\nSUBJECT: a subject\n\nREQUEST:\ndo it\n")


def me_address() -> str:
    who = gzmsg.whoami()
    return f"{who['host']}/{who['agent']}"


@case("inbox main: a delivered REQUEST to this login shows `queued as jN` and is on the list, once; others are not")
def _():
    mine, other = me_address(), "host-a/someone-else"
    served = [0]

    def answer(_h, _method, path, _body):
        if path == "/status":
            return 200, "{}"
        if path.startswith("/api/wait"):
            served[0] += 1
            if served[0] == 1:
                msgs = [{"seq": 5, "id": "r5", "ts": "T", "sender": "host-a/user", "content": request_text(mine, "host-a/user")},
                        {"seq": 6, "id": "r6", "ts": "T", "sender": "host-a/user", "content": request_text(other, "host-a/user")
                         .replace(MID, "01a11f64-0000-7000-8000-000000000002")}]
                return 200, json.dumps({"messages": msgs, "next_cursor": "c"})
            return 200, json.dumps({"messages": [], "next_cursor": "c"})
        return 200, "{}"
    stub = P.Stub(answer)
    out = io.StringIO()
    real = sys.stdout
    try:
        with command_env(CLAUDE_BRIDGE_URL=stub.url) as state:
            sys.stdout = out
            rc = inbox.main([])
            sys.stdout = real
            check(rc == 0, rc)
            shown = out.getvalue()
            check(f"queued as j1: a subject (REQUEST {MID})" in shown and shown.count("queued as") == 1, shown)
            check(shown.index("do it") < shown.index("queued as"), "the delivery first, what it queued below")
            doc = json.load(open([os.path.join(d, f) for d, _, fs in os.walk(state) for f in fs if f == "jobs.json"][0], encoding="utf-8"))
            check(len(doc["jobs"]) == 1 and doc["jobs"][0]["source"]["message_id"] == MID, doc)
    finally:
        sys.stdout = real
        stub.close()


@case("send main: a REQUEST posted by the host operator asks the control plane; a resend (deduplicated) asks nothing")
def _():
    mine = me_address()
    who = gzmsg.whoami()
    results: list[bool] = []

    def answer(_h, _method, path, _body):
        if path == "/status":
            return 200, "{}"
        if path == "/api/send":
            return 200, json.dumps({"seq": 41, "deduplicated": results[-1]})
        return 200, "{}"
    stub = P.Stub(answer)
    real_ctl = intake.CTL
    try:
        with tempfile.TemporaryDirectory() as tmp, command_env(CLAUDE_BRIDGE_URL=stub.url):
            log = os.path.join(tmp, "ctl.log")
            ctl = os.path.join(tmp, "fabric-ctl")
            with open(ctl, "w", encoding="utf-8") as fh:
                fh.write(f'#!/bin/sh\nprintf "%s\\n" "$*" >> {log}\n[ "$2" = jobs ] && exit 0\necho "x added j8"\n')
            os.chmod(ctl, 0o755)
            hosts = os.path.join(tmp, "hosts.json")
            with open(hosts, "w", encoding="utf-8") as fh:
                json.dump({"hosts": {who["host"]: {"operator": who["agent"]}}}, fh)
            os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = hosts
            intake.CTL = ctl
            for dedup, asked in ((False, True), (True, False)):
                results.append(dedup)
                path = os.path.join(tmp, f"msg{dedup}.txt")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(request_text(mine, mine))
                if os.path.exists(log):
                    os.remove(log)
                err, real_err = io.StringIO(), sys.stderr
                sys.stderr = err
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        rc = send.main([path, "--force"])
                finally:
                    sys.stderr = real_err
                calls = open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
                check(rc == 0, (rc, err.getvalue()))
                if asked:
                    check(len(calls) == 2 and calls[1].startswith(f"{who['agent']} jobs-add --project agent-fabric -- a subject (REQUEST {MID})")
                          and f"queued as j8 on {mine}'s job list" in err.getvalue(), (calls, err.getvalue()))
                else:
                    check(calls == [], calls)
    finally:
        intake.CTL = real_ctl
        stub.close()


def main() -> int:
    fails = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok   {name}")
        except Failed as e:
            fails += 1
            print(f"  FAIL {name}: {e}")
    import shutil
    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{'FAILED' if fails else 'all passed'}: {len(CASES) - fails}/{len(CASES)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
