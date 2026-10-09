#!/usr/bin/env python3
"""Tests for tools/fabric/control/sessions.py, the port of runtime/control/sessions.mjs.

sessions.test.mjs's cases are ported case for case, but one: it read an
unreadable state file as no sessions, and j5 (the owner, 2026-10-09)
makes that unknown here; python-dev-02's j5 cases stand in for it. Its
"agentd posts on the state channel" case is agentd's and moves with that
port. Date.parse is held to Node's on the same strings.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import sessions as cs  # noqa: E402


def fake_proc(d, pid, start, comm="claude"):
    os.makedirs(os.path.join(d, str(pid)), exist_ok=True)
    # Field 22 is the start time; a comm may hold spaces and parentheses.
    fields = ["S", "1", *["0"] * 17, str(start), "0", "0"]
    with open(os.path.join(d, str(pid), "stat"), "w") as fh:
        fh.write(f"{pid} ({comm}) {' '.join(fields)}\n")


def ms(text):
    return cs.date_parse(text)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as d:
        proc = os.path.join(d, "proc")
        fake_proc(proc, 100, 5000)
        fake_proc(proc, 200, 6000, "cla (u) de")
        file = os.path.join(d, "session-state.json")

        def write(sessions):
            with open(file, "w") as fh:
                json.dump({"sessions": sessions}, fh)

        def raw(text):
            with open(file, "w") as fh:
                fh.write(text)

        print("sessions.test.mjs: alive")
        check("a process is alive while it is the one recorded", cs.alive(100, 5000, proc) is True)
        check("a reused pid is not the session", cs.alive(100, 5001, proc) is False)
        check("a comm with a parenthesis", cs.alive(200, 6000, proc) is True)
        check("a gone process", cs.alive(300, 1, proc) is False)
        now = ms("2026-10-08T12:00:00Z")
        check("no process recorded, fresh: kept", cs.alive(None, None, proc, since="2026-10-08T11:45:00Z", now_ms=now) is True)
        edge = now - cs.NO_PROCESS_FRESH_MS
        import datetime
        iso = lambda t: datetime.datetime.fromtimestamp(t / 1000, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        check("...to the edge of two heartbeats", cs.alive(None, None, proc, since=iso(edge), now_ms=now) is True)
        check("older than two heartbeats: not believed", cs.alive(None, None, proc, since=iso(edge - 1000), now_ms=now) is False)
        check("a since that is not a time: not believed", cs.alive(None, None, proc, since="never", now_ms=now) is False)
        check("a pid of 100.0 is the integer 100, as JSON.parse reads it", cs.alive(100.0, 5000.0, proc) is True)

        print("sessions.test.mjs: no process, stale")
        write({"probe": {"state": "idle", "since": "2026-10-08T11:00:00Z", "pid": None, "start": None},
               "young": {"state": "idle", "since": "2026-10-08T11:59:00Z"}})
        stale = []
        check("an entry with no process is left out once stale",
              cs.read_sessions(file, proc=proc, now_ms=now, on_stale=stale.append) == [{"session": "young", "state": "idle", "since": "2026-10-08T11:59:00Z"}])
        check("...naming it", stale == ["probe"])
        logs, t = [], [now]
        w = cs.StateWatcher(address="h/x", post=lambda r: None, file=file, proc=proc, now=lambda: t[0], heartbeat_ms=1, log=logs.append)
        w.tick()
        t[0] += 5
        w.tick()
        check("...and the watcher says so once", [m for m in logs if "probe" in m] ==
              ["agentd: session probe records no process and its state is older than 20 min; left out"], logs)

        print("sessions.test.mjs: readSessions")
        os.remove(file)
        check("no file: none", cs.read_sessions(file, proc=proc) == [])
        write({"b": {"state": "working", "since": "t1", "pid": 100, "start": 5000},
               "a": {"state": "blocked", "since": "t2", "pid": 200, "start": 6000},
               "dead": {"state": "idle", "since": "t3", "pid": 300, "start": 1},
               "reused": {"state": "idle", "since": "t4", "pid": 100, "start": 4999},
               "odd": {"state": "sleeping", "since": "t5", "pid": 100, "start": 5000}})
        check("live sessions in a known state, sorted, without the process",
              cs.read_sessions(file, proc=proc) == [{"session": "a", "state": "blocked", "since": "t2"},
                                                    {"session": "b", "state": "working", "since": "t1"}])

        print("j5: a file that is there but cannot be read is unknown")
        for text in ("{broken", "[]", "null", "7", "{}", '{"sessions": []}', '{"sessions": null}', '{"sessions": "x"}', "NaN"):
            raw(text)
            check(f"{text!r}: unknown", cs.read_sessions(file, proc=proc) is None)
        raw('{"sessions": {}}')
        check('{"sessions": {}}: none', cs.read_sessions(file, proc=proc) == [])
        os.remove(file)
        os.mkdir(file)
        check("a directory where the file should be (a read error, not absent): unknown", cs.read_sessions(file, proc=proc) is None)
        os.rmdir(file)

        print("j5, as fabric-coordinator decided (REPLY 01a11ec9-b9e8): no state posted while unknown")
        write({})
        posts, logs, t = [], [], [0.0]
        w = cs.StateWatcher(address="h/x", post=posts.append, file=file, proc=proc, now=lambda: t[0], heartbeat_ms=60_000, log=logs.append)
        check("a readable file is posted", w.tick() is True and posts[-1]["sessions"] == [])
        raw("{broken")
        t[0] += 2000
        check("the file broken: nothing is posted, never a wrong none", w.tick() is False and len(posts) == 1)
        t[0] += 2000
        check("a tick 2 s later posts nothing either", w.tick() is False and len(posts) == 1)
        t[0] += 60_000
        check("nor the heartbeat: the last record goes stale at the listener", w.tick() is False and len(posts) == 1)
        check("nothing posted says unreadable", all(p["sessions"] != "unreadable" for p in posts))
        raw('{"sessions": {}}')
        t[0] += 2000
        check("readable again: posted at once, though nothing changed since the last record", w.tick() is True and posts[-1]["sessions"] == [])
        check("the log holds exactly two lines, down and back",
              logs == [f"{file} cannot be read; no state posted until it reads again", f"{file} is readable again"], logs)
        raw("{broken")
        t[0] += 1000
        check("broken again", w.tick() is False)
        raw('{"sessions": {}}')
        t[0] += 2000
        check("readable 3 s later, inside the heartbeat, the same as last said: posted at once", w.tick() is True and len(posts) == 3)
        raw("{broken")
        posts2 = []
        w2 = cs.StateWatcher(address="h/x", post=posts2.append, file=file, proc=proc, now=lambda: 0.0, log=lambda m: None)
        check("a watcher that starts on a broken file posts nothing at all", w2.tick() is False and posts2 == [])

        print("sessions.test.mjs: when the watcher posts")
        binding = os.path.join(d, "binding.json")
        with open(binding, "w") as fh:
            json.dump({"role": "backend-dev", "project": "gzapp", "session": "s", "working_copy": "/home/x/projects/private-wc", "pid": 31337}, fh)
        os.remove(file)
        posts, t = [], [1_000_000.0]
        w = cs.StateWatcher(address="h/x", post=posts.append, file=file, binding=binding, proc=proc, now=lambda: t[0],
                            heartbeat_ms=60_000, log=lambda m: None)
        check("the first tick says what there is", w.tick() is True)
        check("...a State, the binding's role and project",
              posts[0] == {"v": 1, "kind": "state", "from": "h/x", "ts": "1970-01-01T00:16:40.000Z", "sessions": [], "role": "backend-dev",
                           "project": "gzapp"}, posts[0])
        t[0] += 2000
        check("nothing changed: nothing posted", w.tick() is False)
        write({"s": {"state": "working", "since": "x", "pid": 100, "start": 5000}})
        t[0] += 2000
        check("a new session", w.tick() is True and posts[1]["sessions"] == [{"session": "s", "state": "working", "since": "x"}])
        import shutil
        shutil.rmtree(os.path.join(proc, "100"))
        t[0] += 2000
        check("its process died: said, with no SessionEnd", w.tick() is True and posts[2]["sessions"] == [])
        with open(binding, "w") as fh:
            json.dump({"role": "web-dev", "project": "gzapp"}, fh)
        t[0] += 2000
        check("a rebind is a change", w.tick() is True)
        t[0] += 59_000
        check("...then nothing", w.tick() is False)
        t[0] += 2000
        check("the heartbeat re-says it", w.tick() is True and len(posts) == 5)
        said = json.dumps(posts)
        check("no path, no binding field but role and project, no process id or start time",
              not any(x in said for x in ("private-wc", "31337", '"pid"', '"start"', "5000")))
        fake_proc(proc, 100, 5000)

        print("sessions.test.mjs: a failed post, a post in flight")
        logs, posts, fail = [], [], [2]

        def flaky(r):
            if fail[0] > 0:
                fail[0] -= 1
                raise OSError("relay down")
            posts.append(r)
        w = cs.StateWatcher(address="h/x", post=flaky, file=file, proc=proc, log=logs.append)
        check("a failed post is retried", w.tick() is False and w.tick() is False and w.tick() is True and len(posts) == 1)
        check("...and said once: one line down, one back", len(logs) == 2, logs)
        calls = []

        def reentrant(r):
            calls.append(r)
            check("a tick while a post is in flight does nothing", w2.tick() is False)
        w2 = cs.StateWatcher(address="h/x", post=reentrant, file=file, proc=proc, log=lambda m: None)
        check("...and the first completes", w2.tick() is True and len(calls) == 1)

        print("sessions.test.mjs: waits_on")
        jobs = os.path.join(d, "jobs.json")
        A, B = "01a11a18-4728-7d8b-afd9-0edb2d30a59c", "01a11a19-0bea-70c7-b667-1e1e5a74dbe1"
        check("no list: none", cs.waits_on(jobs) == [])
        with open(jobs, "w") as fh:
            fh.write("{broken")
        check("unreadable: unknown, never none", cs.waits_on(jobs) is None)
        with open(jobs, "w") as fh:
            fh.write('{"jobs": 3}')
        check("not a job list: unknown", cs.waits_on(jobs) is None)
        with open(jobs, "w") as fh:
            json.dump({"jobs": [{"id": "j1", "state": "blocked", "title": "secret title", "waits_on": B},
                                {"id": "j2", "state": "blocked", "title": "x", "waits_on": A},
                                {"id": "j3", "state": "queued", "title": "x", "waits_on": "01a11a20-0000-7000-8000-000000000000"},
                                {"id": "j4", "state": "blocked", "title": "x", "waits_on": "not an id; rm -rf"},
                                {"id": "j5", "state": "blocked", "title": "x", "blocked_on": "a reply"},
                                {"id": "j6", "state": "blocked", "title": "x", "waits_on": A},
                                {"id": "j7", "state": "blocked", "title": "x", "waits_on": A + "\n"}]}, fh)
        check("blocked, well-formed, de-duplicated, sorted (a trailing newline is no id)", cs.waits_on(jobs) == [A, B], cs.waits_on(jobs))
        posts, t = [], [0.0]
        w = cs.StateWatcher(address="h/x", post=posts.append, file=file, jobs=jobs, proc=proc, now=lambda: t[0], heartbeat_ms=60_000, log=lambda m: None)
        w.tick()
        check("the record carries them", posts[-1]["waits_on"] == [A, B])
        check("no title, no job id", "secret title" not in json.dumps(posts) and '"j1"' not in json.dumps(posts))
        with open(jobs, "w") as fh:
            json.dump({"jobs": [{"id": "j1", "state": "active", "title": "x", "waits_on": B}]}, fh)
        t[0] = 1
        check("a job unblocked is a change; waiting on nothing, the key is absent", w.tick() is True and "waits_on" not in posts[-1])
        with open(jobs, "w") as fh:
            json.dump({"jobs": [{"id": "j1", "state": "blocked", "title": "x", "waits_on": A}]}, fh)
        posts, logs, t = [], [], [0.0]
        w = cs.StateWatcher(address="h/x", post=posts.append, file=file, jobs=jobs, proc=proc, now=lambda: t[0], heartbeat_ms=60_000, log=logs.append)
        w.tick()
        with open(jobs, "w") as fh:
            fh.write("{broken")
        t[0] = 61_000
        w.tick()
        t[0] = 122_000
        w.tick()
        check("an unreadable job list keeps the waits_on last said", [p.get("waits_on") for p in posts] == [[A], [A], [A]])
        check("...and is logged once", len([m for m in logs if "cannot be read" in m]) == 1, logs)
        os.remove(jobs)
        t[0] = 123_000
        check("no list at all waits on nothing", w.tick() is True and "waits_on" not in posts[-1])

        print("sessions.test.mjs: the record")
        check("a role and project it does not have are left out",
              cs.state_record("h/x", {"sessions": [], "role": None, "project": None}, "t") == {"v": 1, "kind": "state", "from": "h/x", "ts": "t", "sessions": []})
        cfg = os.path.join(d, "claude")
        sid = "0f0e0d0c-1111-4222-8333-444455556666"
        with open(binding, "w") as fh:
            json.dump({"role": "python-dev", "project": "agent-fabric", "session": sid, "working_copy": "/home/x/projects/private-wc"}, fh)
        write({})
        posts, t = [], [0.0]
        w = cs.StateWatcher(address="h/x", post=posts.append, file=file, binding=binding, proc=proc, now=lambda: t[0],
                            heartbeat_ms=60_000, log=lambda m: None, config_dir=cfg)
        w.tick()
        check("the last session's id", posts[-1].get("last_session") == sid)
        check("...not resumable without a transcript", posts[-1].get("resumable") is False)
        os.makedirs(os.path.join(cfg, "projects", "-home-x-projects"))
        with open(os.path.join(cfg, "projects", "-home-x-projects", f"{sid}.jsonl"), "w") as fh:
            fh.write("{}\n")
        t[0] = 1
        w.tick()
        check("the transcript appeared: resumable, posted as a change", posts[-1].get("resumable") is True)
        check("no path leaves the account", "private-wc" not in json.dumps(posts) and "-home-x-projects" not in json.dumps(posts))
        os.makedirs(os.path.join(cfg, "etc"))
        with open(os.path.join(cfg, "etc", "x.jsonl"), "w") as fh:
            fh.write("{}\n")
        check("an id that is not one is never looked up", cs.transcript_exists("../../etc/x", cfg) is False)
        for bad in ("../../etc/x", "abc\u001b]0;t\u0007def", 42):
            with open(binding, "w") as fh:
                json.dump({"role": "python-dev", "project": "agent-fabric", "session": bad}, fh)
            t[0] += 1
            w.tick()
            check(f"a binding session {bad!r} is no session", "last_session" not in posts[-1] and "resumable" not in posts[-1])
        check("no last session: neither field",
              cs.state_record("h/x", {"sessions": [], "role": None, "project": None, "last_session": None}, "t")
              == {"v": 1, "kind": "state", "from": "h/x", "ts": "t", "sessions": []})

    print("Date.parse, as Node reads it")
    cases = ["2026-10-08T12:00:00Z", "2026-10-08T12:00:00.123Z", "2026-10-08", "2026-02-29", "2026-10-08t12:00:00z", "-000001-01-01T00:00:00Z",
             "2026-10-08T12:00:00+02:00", "2026-10-08T24:00:00Z", "2026-13-01", "never", "", "2026-10-08T12:00"]
    r = subprocess.run(["node", "-e", "const c=JSON.parse(require('fs').readFileSync(0,'utf8'));"
                        "process.stdout.write(JSON.stringify(c.map(s=>{const t=Date.parse(s);return Number.isNaN(t)?'NaN':t;})))"],
                       input=json.dumps(cases), capture_output=True, text=True, timeout=60, env={**os.environ, "TZ": "Europe/Rome"})
    node = json.loads(r.stdout) if r.returncode == 0 else r.stderr
    saved = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Rome"
    import time as _t
    _t.tzset()
    mine = ["NaN" if math.isnan(cs.date_parse(c)) else cs.date_parse(c) for c in cases]
    if saved is None:
        os.environ.pop("TZ")
    else:
        os.environ["TZ"] = saved
    _t.tzset()
    check("date_parse is Date.parse on ISO strings and near-misses (Europe/Rome)", mine == node, list(zip(cases, node, mine)))

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
