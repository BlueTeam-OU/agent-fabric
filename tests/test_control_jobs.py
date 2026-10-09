#!/usr/bin/env python3
"""Tests for tools/fabric/control/jobs.py, the port of runtime/control/jobs.mjs.

jobs.test.mjs's cases of jobs.mjs are ported case for case, through the
real tools/fabric/jobs.py against a scratch state directory. Its cases
of OPS / PUBLIC_OPS (ops.mjs) and of fabric-ctl's parseArgs and table
(ctl.mjs) move with those ports. Beyond them: check_job_args and the
list's mapping are held to Node's own on the same inputs, since a
request from a Node fabric-ctl must be refused or run alike here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import jobs as cj  # noqa: E402
import jobs as jobs_tool  # noqa: E402

JOBS_MJS = os.path.join(HERE, "runtime", "control", "jobs.mjs")


def node(js: str, data):
    r = subprocess.run(["node", "--input-type=module", "-e",
                        f"import fs from 'node:fs'; import * as m from '{JOBS_MJS}'; const input = JSON.parse(fs.readFileSync(0, 'utf8')); "
                        f"const out = await (async () => {{ {js} }})(); process.stdout.write(JSON.stringify(out));"],
                       input=json.dumps(data), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-400:])
    return json.loads(r.stdout)


def done(stdout="", stderr="", code=0):
    return lambda argv, **kw: SimpleNamespace(stdout=stdout, stderr=stderr, returncode=code, argv=argv, kw=kw)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    print("jobs.test.mjs: jobs-add takes a closed set of plain arguments")
    c = cj.check_job_args
    check("a title", c({"title": "ship it"}) is None)
    check("a title, a topic, a project", c({"title": "ship it", "topic": "drain", "project": "gzapp"}) is None)
    check("an extra argument", "only title, topic, project and priority" in c({"title": "x", "command": "rm"}))
    check("an empty title", "title is one line" in c({"title": ""}))
    check("a title of two lines", "title is one line" in c({"title": "a\nb"}))
    check("a title of 301", "title is one line" in c({"title": "x" * 301}))
    check("a project that is a path", "registry id" in c({"title": "x", "project": "../etc"}))
    check("no arguments", "takes { title" in c(None))
    check("a priority", c({"title": "x", "priority": "blocking"}) is None)
    check("a priority not on the list", "priority is one of blocking, high, normal, low" in c({"title": "x", "priority": "urgent"}))
    check("a C1 control is refused like a C0 one",
          "title is one line" in c({"title": "a\u009b31mred"}) and "topic is one line" in c({"title": "t", "topic": "x\u0085y"}))
    check("PRIORITIES is jobs.py's", cj.PRIORITIES == list(jobs_tool.PRIORITIES), (cj.PRIORITIES, jobs_tool.PRIORITIES))

    print("...and judged as Node judges them")
    battery = [None, [], "x", 5, {}, {"title": None}, {"title": 5}, {"title": " "}, {"title": "\ufeff"}, {"title": "\u180e"},
               {"title": "\u3000a"}, {"title": "\U0001f600" * 150}, {"title": "\U0001f600" * 151}, {"title": "\u00e9" * 300},
               {"title": "x", "topic": None}, {"title": "x", "topic": ""}, {"title": "x", "topic": "t" * 61},
               {"title": "x", "project": None}, {"title": "x", "project": 5}, {"title": "x", "project": True},
               {"title": "x", "project": "gzapp\n"}, {"title": "x", "project": ["a"]}, {"title": "x", "project": ["a", "b"]},
               {"title": "x", "project": {}}, {"title": "x", "project": "A"}, {"title": "x", "project": "-x"},
               {"title": "x", "priority": None}, {"title": "x", "priority": 1}, {"title": "x", "priority": ["high"]},
               {"title": "x", "2": 1, "1": 2, "b": 3, "a": 4}, {"title": "x", "01": 1, "4294967295": 2, "4294967294": 3},
               {"title": "x\u007f"}, {"title": "x\u00a0"}, {"title": "x", "topic": "\u2028"}]
    want = node("return input.map(a => m.checkJobArgs(a));", battery)
    got = [c(a) for a in battery]
    differ = [(a, w, g) for a, w, g in zip(battery, want, got) if w != g]
    check(f"check_job_args says what checkJobArgs says, on {len(battery)} argument sets", not differ, differ[:4])

    print("jobs.test.mjs: jobs")
    listed = [{"id": "j1", "state": "queued", "title": "a", "priority": None}, {"id": "j2", "state": "queued", "title": "b"},
              {"id": "j3", "state": "active", "title": "c", "project": "", "topic": None, "source": {"kind": ""},
               "blocked_on": "x", "artifacts": None, "updated": "t", "log": [1]},
              {"id": "j4", "state": "done", "title": "d", "source": "a string", "artifacts": ["PR #1"]},
              {"id": "j5", "state": "queued", "title": "e", "source": {"from": "h/u"}, "priority": "high"}]
    got = cj.jobs(run=done(json.dumps(listed)))
    check("a priority stored as null is unknown, never normal; an absent one is normal",
          [j["priority"] for j in got["jobs"]][:2] == [None, "normal"])
    nodes = node("return await m.jobs({ exec: async () => JSON.stringify(input) });", listed)
    check("the list is mapped as Node maps it, field for field (?? is null only)", got == nodes, (got, nodes))
    for label, run in (("a failed list", done("", "fabric-jobs: broken\n", 1)), ("an answer that is not JSON", done("nope")),
                       ("an answer that is not a list", done('{"a": 1}'))):
        try:
            cj.jobs(run=run)
            check(f"{label} is JobsError", False)
        except cj.JobsError:
            check(f"{label} is JobsError, never an empty list", True)

    print("jobs.test.mjs: jobs-add, through the real jobs.py")
    saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as state:
        os.environ["AGENT_FABRIC_STATE_DIR"] = state
        try:
            r = cj.jobs_add({"from": "h/op", "to": ["h/a"], "args": {"title": "first", "priority": "high"}}, home=home, root=HERE)
            check("jobs-add carries a priority to the list", r.get("status") == "added" and r["job"].split()[:3] == ["j1", "queued", "high"], r)
            cj.jobs_add({"from": "h/op", "to": ["h/a"], "args": {"title": "second"}}, home=home, root=HERE)
            got = cj.jobs(home=home, root=HERE)
            check("...and jobs reads it; a job without one reads normal", [j["priority"] for j in got["jobs"]] == ["high", "normal"], got)
        finally:
            if saved is None:
                os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
            else:
                os.environ["AGENT_FABRIC_STATE_DIR"] = saved
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as state:
        os.environ["AGENT_FABRIC_STATE_DIR"] = state
        try:
            r = cj.jobs_add({"from": "develop-qzapp/user", "to": ["develop-qzapp/user"],
                             "args": {"title": "-a title with a leading dash", "topic": "routing"}}, home=home, root=HERE)
            check("the owner's job is added", r.get("status") == "added" and r["job"].split()[:2] == ["j1", "queued"], r)
            got = cj.jobs(home=home, root=HERE)
            j = got["jobs"][0] if got.get("jobs") else {}
            check("jobs reads it back: a dash-leading title is a title, the source the owner",
                  got["status"] == "ok" and len(got["jobs"]) == 1
                  and [j.get(k) for k in ("id", "state", "title", "topic", "source")] == ["j1", "queued", "-a title with a leading dash",
                                                                                      "routing", "owner"], got)
            check("...without its log", "log" not in j)
            login = os.listdir(os.path.join(state, "agents"))[0]
            with open(os.path.join(state, "agents", login, "jobs.json"), encoding="utf-8") as fh:
                doc = json.load(fh)
            check("the list records the owner's address", doc["jobs"][0]["source"] == {"kind": "owner", "from": "develop-qzapp/user"},
                  doc["jobs"][0].get("source"))
        finally:
            if saved is None:
                os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
            else:
                os.environ["AGENT_FABRIC_STATE_DIR"] = saved

    print("jobs.test.mjs: refusals")
    ran = []

    def spy(argv, **kw):
        ran.append(argv)
        return SimpleNamespace(stdout="added j1 queued", stderr="", returncode=0)
    r = cj.jobs_add({"from": "h/op", "to": ["h/a"], "args": {"title": "x", "extra": 1}}, run=spy)
    check("a refused jobs-add runs nothing", r["status"] == "refused" and not ran, (r, ran))
    r = cj.jobs_add({"from": "h/op", "to": ["h/a"], "args": {"title": "x"}},
                    run=done("", "fabric-jobs: identity: jobs.json is not a job list\n", 1))
    check("...and says why fabric-jobs refused", r == {"status": "refused", "reason": "identity: jobs.json is not a job list"}, r)
    for to in ("*", ["h/a", "h/b"], ["*"]):
        r = cj.jobs_add({"from": "h/op", "to": to, "args": {"title": "t"}}, run=spy)
        check(f"the daemon refuses a jobs-add addressed to {to!r}", r == {"status": "refused", "reason": "jobs-add names one login, never all"})
    check("...having run nothing", not ran)
    check("one login is added", cj.jobs_add({"from": "h/op", "to": ["h/a"], "args": {"title": "t"}}, run=spy)["status"] == "added")
    check("...by argv: the owner, then -- before the title", ran[-1][1:] == ["add", "--owner", "h/op", "--", "t"], ran[-1])
    r = cj.jobs_add({"from": "h/op", "to": ["h/a"], "args": {"title": "t", "project": "x"}},
                    run=done("added j3    queued    x: t\n", "  no working copy of x found beside this one: re-add it\n"))
    check("fabric-jobs's warning is carried to the owner", r.get("warning") == "no working copy of x found beside this one: re-add it", r)

    def late(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout"))
    r = cj.jobs_add({"from": "h/op", "to": ["h/a"], "args": {"title": "t"}}, run=late)
    check("a jobs.py that never answers is refused with the bound, never an empty reason",
          r == {"status": "refused", "reason": "no answer within 15 s"}, r)

    print("...and run as Node runs them")
    shapes = [{"from": "h/op", "to": "h/a", "args": {"title": "t", "topic": "x", "project": "p", "priority": "low"}},
              {"from": 5, "to": ["h/a"], "args": {"title": "-t", "project": None}},
              {"from": None, "to": ["h/a"], "args": {"title": "t", "project": 7}}]
    want = node("const seen = []; for (const r of input) await m.jobsAdd(r, { root: '/R', home: '/H', "
                "exec: async (cmd, argv) => { seen.push(argv.slice(1).map(String)); return { stdout: 'added j1', stderr: '' }; } }); return seen;", shapes)
    seen = []

    def record(argv, **kw):
        seen.append(argv[1:])
        return SimpleNamespace(stdout="added j1", stderr="", returncode=0)
    for r in shapes:
        cj.jobs_add(r, home="/H", root="/R", run=record)
    # execFile spawns String() of each argument, so Node's argv is read as the child receives it.
    check("jobs.py's argv is Node's, String() of each value", seen == want, (seen, want))
    r = subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "jobs.py"), "--help"], capture_output=True, timeout=60)
    check("the jobs tool the ops run exists where they look for it", r.returncode == 0, r.stderr[-200:])

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
