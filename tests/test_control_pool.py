#!/usr/bin/env python3
"""Tests for tools/fabric/control/pool.py, the port of runtime/control/pool.mjs.

pool.test.mjs's cases of pool.mjs are ported case for case; its cases of
OPS / PUBLIC_OPS, agentd's accept and answer, and fabric-ctl's parsing
move with those ports. Beyond them, the pool file is frozen with the
wire: Node and Python write the same bytes for the same adds and claims,
and each continues the other's file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import pool as cp  # noqa: E402

HOLDER = "h/user"
KNOWN = {"python-dev", "web-dev"}
POOL_MJS = os.path.join(HERE, "runtime", "control", "pool.mjs")
CTL_MJS = os.path.join(HERE, "runtime", "control", "ctl.mjs")


def roles(mapping):
    return lambda address: {"role": mapping[address]} if address in mapping else {"error": f"no state record from {address}"}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    def fresh(d):
        file = os.path.join(d, "pool.json")
        n = [0]

        def add(args, sender=HOLDER):
            stamp = f"2026-10-08T00:00:0{n[0]}Z"
            n[0] += 1
            return cp.pool_add({"from": sender, "to": [HOLDER], "args": args}, me=HOLDER, holder=HOLDER, file=file, known=KNOWN,
                               now=lambda: stamp)
        return file, add

    r = subprocess.run(["node", "--input-type=module", "-e",
                        f"import {{STATES_REPLAY, STATES_STALE_MS}} from '{CTL_MJS}'; process.stdout.write(JSON.stringify([STATES_REPLAY, STATES_STALE_MS]))"],
                       capture_output=True, text=True, timeout=60)
    check("STATES_REPLAY and STATES_STALE_MS are ctl.mjs's", r.returncode == 0 and json.loads(r.stdout) == [cp.STATES_REPLAY, cp.STATES_STALE_MS],
          r.stdout or r.stderr[-200:])

    with tempfile.TemporaryDirectory() as d:
        print("pool.test.mjs: the holder")
        reg = os.path.join(d, "registry.json")
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h": {"operator": "user"}}}, fh)
        check("the operator of the one host", cp.pool_holder({}, reg) == "h/user")
        check("configured, it wins", cp.pool_holder({"pool_holder": "k/coord"}, reg) == "k/coord")
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h": {"operator": "user"}, "k": {"operator": "op"}}}, fh)
        check("two hosts, none configured: never guessed", cp.pool_holder({}, reg) is None)
        check("no registry: nobody", cp.pool_holder({}, os.path.join(d, "missing.json")) is None)
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h": {}}}, fh)
        check("an operator not named is user", cp.pool_holder({}, reg) == "h/user")

    with tempfile.TemporaryDirectory() as d:
        print("pool.test.mjs: pool-add")
        file, add = fresh(d)
        check("a closed argument set", "only role, title, topic, project and priority" in add({"role": "python-dev", "title": "x", "extra": 1})["reason"])
        check("a catalogue role", "no role nobody in the catalogue" in add({"role": "nobody", "title": "x"})["reason"])
        check("a priority of the list", "priority is one of" in add({"role": "python-dev", "title": "x", "priority": "urgent"})["reason"])
        check("a role at all", "role is a catalogue id" in add({"title": "x"})["reason"])
        check("a catalogue that cannot be read", "catalogue cannot be read" in cp.check_pool_args({"role": "python-dev", "title": "x"}, None))
        check("a refused add writes nothing", cp.read_pool(file)["jobs"] == [])
        r = add({"role": "python-dev", "title": "  port   the thing ", "priority": "high", "topic": "port"})
        check("an add", r.get("status") == "added", r)
        check("...its id, role, squashed title, priority, topic",
              [r["job"][k] for k in ("id", "role", "title", "priority", "topic")] == ["p1", "python-dev", "port the thing", "high", "port"], r)
        check("ids in order", add({"role": "web-dev", "title": "y"})["job"]["id"] == "p2")
        check("no priority is normal", cp.read_pool(file)["jobs"][1]["priority"] == "normal")
        check("the file is 0600", os.stat(file).st_mode & 0o777 == 0o600)

        print("pool.test.mjs: pool-add only on the holder")
        req = {"from": HOLDER, "to": ["h/other"], "args": {"role": "python-dev", "title": "x"}}
        check("another account does not hold it", "h/user does" in cp.pool_add(req, me="h/other", holder=HOLDER, file=file, known=KNOWN)["reason"])
        check("addressed to it alone", "only it" in cp.pool_add({**req, "to": "*"}, me=HOLDER, holder=HOLDER, file=file, known=KNOWN)["reason"])
        check("no holder at all", "no account holds the pool" in cp.pool_add({**req, "to": [HOLDER]}, me=HOLDER, holder=None, file=file, known=KNOWN)["reason"])

    with tempfile.TemporaryDirectory() as d:
        print("pool.test.mjs: pool-list")
        file, add = fresh(d)
        add({"role": "python-dev", "title": "old normal"})
        add({"role": "web-dev", "title": "not mine"})
        add({"role": "python-dev", "title": "low", "priority": "low"})
        add({"role": "python-dev", "title": "high", "priority": "high"})
        add({"role": "python-dev", "title": "newer high", "priority": "high"})

        def listed():
            return [j["id"] for j in cp.pool_list({"from": "h/a", "args": {"role": "python-dev"}}, me=HOLDER, holder=HOLDER, file=file)["jobs"]]
        check("the role's open jobs, highest priority then oldest", listed() == ["p4", "p5", "p1", "p3"], listed())
        cp.pool_claim({"from": "h/a", "args": {"id": "p4"}}, me=HOLDER, holder=HOLDER, file=file, role_of=roles({"h/a": "python-dev"}))
        check("claimed ones gone", listed() == ["p5", "p1", "p3"])
        check("an empty pool is said as one",
              cp.pool_list({"from": "h/a", "args": {"role": "db-admin"}}, me=HOLDER, holder=HOLDER, file=file) == {"status": "ok", "role": "db-admin", "jobs": []})
        check("pool-list takes { role }", "takes { role }" in cp.pool_list({"from": "h/a", "args": {}}, me=HOLDER, holder=HOLDER, file=file)["reason"])

    with tempfile.TemporaryDirectory() as d:
        print("pool.test.mjs: pool-claim")
        file, add = fresh(d)
        add({"role": "python-dev", "title": "x"})

        def claim(sender, args, mapping):
            return cp.pool_claim({"from": sender, "args": args}, me=HOLDER, holder=HOLDER, file=file, role_of=roles(mapping))
        r = claim("h/web", {"id": "p1", "role": "python-dev"}, {"h/web": "web-dev"})
        check("the claimant's reported role decides, never one the request names",
              r["status"] == "refused" and "h/web holds web-dev, as its control agent reports it; p1 is for python-dev" in r["reason"], r)
        check("...nothing claimed", cp.read_pool(file)["jobs"][0]["claimed"] is None)
        check("no record: refused", "no state record from h/gone" in claim("h/gone", {"id": "p1"}, {})["reason"])
        check("no such job", "no pool job p9" in claim("h/py", {"id": "p9"}, {"h/py": "python-dev"})["reason"])
        check("an id that is not one", "a pool job id" in claim("h/py", {"id": "../p1"}, {"h/py": "python-dev"})["reason"])
        won = claim("h/py", {"id": "p1"}, {"h/py": "python-dev"})
        check("claimed", won["status"] == "claimed" and cp.read_pool(file)["jobs"][0]["claimed"]["by"] == "h/py", won)
        check("another claimant is refused", "p1 is claimed by h/py" in claim("h/py2", {"id": "p1"}, {"h/py2": "python-dev"})["reason"])
        again = claim("h/py", {"id": "p1"}, {"h/py": "python-dev"})
        check("the claimant again gets it again", [again["status"], again.get("again")] == ["claimed", True], again)
        check("no state stream: refused",
              "reads no state stream" in cp.pool_claim({"from": "h/py", "args": {"id": "p1"}}, me=HOLDER, holder=HOLDER, file=file)["reason"])

    with tempfile.TemporaryDirectory() as d:
        print("pool.test.mjs: two claims of one job, interleaved where Node's await is")
        file, add = fresh(d)
        add({"role": "python-dev", "title": "x"})
        out = {}

        def role_of_a(address):
            # b's whole claim runs while a waits on its role read, as the event loop interleaves them.
            out["b"] = cp.pool_claim({"from": "h/b", "args": {"id": "p1"}}, me=HOLDER, holder=HOLDER, file=file, role_of=roles({"h/b": "python-dev"}))
            return {"role": "python-dev"}
        out["a"] = cp.pool_claim({"from": "h/a", "args": {"id": "p1"}}, me=HOLDER, holder=HOLDER, file=file, role_of=role_of_a)
        check("one wins, one is refused", sorted([out["a"]["status"], out["b"]["status"]]) == ["claimed", "refused"], out)
        check("...the loser told it is claimed", "is claimed by" in out["a"]["reason"] and cp.read_pool(file)["jobs"][0]["claimed"]["by"] == "h/b", out)

    with tempfile.TemporaryDirectory() as d:
        print("pool.test.mjs: an unreadable pool")
        file, add = fresh(d)
        add({"role": "python-dev", "title": "x"})
        with open(file, "w") as fh:
            fh.write("{broken")
        check("an add is refused, never onto an empty pool", "not JSON" in add({"role": "python-dev", "title": "y"})["reason"])
        check("...nothing written over it", open(file).read() == "{broken")
        check("a claim is refused", "not JSON" in cp.pool_claim({"from": "h/a", "args": {"id": "p1"}}, me=HOLDER, holder=HOLDER, file=file,
                                                               role_of=roles({"h/a": "python-dev"}))["reason"])
        check("a list is refused", "not JSON" in cp.pool_list({"from": "h/a", "args": {"role": "python-dev"}}, me=HOLDER, holder=HOLDER, file=file)["reason"])
        for text, said in (('{"jobs": [], "seq": 1.5}', "not a pool"), ('{"jobs": {}, "seq": 1}', "not a pool"), ("[]", "not a pool"), ("NaN", "not JSON")):
            with open(file, "w") as fh:
                fh.write(text)
            try:
                cp.read_pool(file)
                check(f"{text}: {said}", False)
            except cp.PoolError as e:
                check(f"{text}: {said}", said in str(e), str(e))
        os.remove(file)
        os.mkdir(file)
        try:
            cp.read_pool(file)
            check("a directory where the pool should be: cannot be read", False)
        except cp.PoolError as e:
            check("a directory where the pool should be: cannot be read (EISDIR)", "cannot be read (EISDIR)" in str(e), str(e))

    print("pool.test.mjs: the claimant's role from the state stream")
    now = 1791460800000.0   # 2026-10-08T12:00:00Z

    def rec(sender, role, ts="2026-10-08T11:59:00Z"):
        return {"content": json.dumps({"v": 1, "kind": "state", "from": sender, "ts": ts, "sessions": [], **({"role": role} if role else {})})}
    asked = []

    def of(rows):
        return cp.role_from_stream(call=lambda p: asked.append(p) or {"messages": rows}, cfg={"state_channel": "s:state:control"}, now=lambda: now)
    check("its newest state record", of([rec("h/a", "web-dev"), rec("h/a", "python-dev"), rec("h/b", "db-admin")])("h/a") == {"role": "python-dev"})
    check("...asked of the state channel", "channel=s%3Astate%3Acontrol" in asked[0], asked[0])
    check("stale", "binding is unknown" in of([rec("h/a", "python-dev", "2026-10-08T11:00:00Z")])("h/a")["error"])
    check("no bound role", "no bound role" in of([rec("h/a", None)])("h/a")["error"])
    check("no record", "no state record from h/a" in of([])("h/a")["error"])
    busy = [rec("h/b", "db-admin", "2026-10-08T11:55:00Z") for _ in range(cp.STATES_REPLAY)]
    check("a full page newer than the bound has not seen the whole of it",
          "last 500 records reach back only 5 min and none is from h/a" in of(busy)("h/a")["error"], of(busy)("h/a"))
    covered = busy[1:250] + [rec("h/b", "db-admin", "2026-10-08T11:30:00Z")] + busy[250:]
    check("a page that covers the bound, by its own ts", "no state record from h/a in the last 20 min" in of(covered)("h/a")["error"])
    check("a page short of full is the whole stream", "no state record from h/a in the last 20 min" in of(busy[1:])("h/a")["error"])
    garbled = covered[:300] + [rec("h/b", "db-admin", "garbage")] + covered[301:]
    check("an unparseable ts says nothing of the span", "no state record from h/a in the last 20 min" in of(garbled)("h/a")["error"])
    from control import gzcoord as cg

    def refused_call(p):
        raise cg.ApiError("x", status=503)
    check("a relay that refuses", "could not be read (the relay refused (HTTP 503))" in cp.role_from_stream(call=refused_call, cfg={"state_channel": "s"})("h/a")["error"])

    def silent_call(p):
        raise cg.ApiError("x -> no answer within 30 s", timed_out=True)
    check("a relay that never answers is never said as unreachable",
          "the relay at http://r did not answer" in cp.role_from_stream(call=silent_call, cfg={"state_channel": "s", "relay_url": "http://r"})("h/a")["error"])

    print("the pool file, frozen with the wire: Node's bytes, and each continues the other's")
    with tempfile.TemporaryDirectory() as d:
        steps = [["add", {"role": "python-dev", "title": " port \u00e9  it ", "topic": "t", "priority": "high"}],
                 ["add", {"role": "web-dev", "title": "x", "project": "gzapp"}], ["claim", "p1", "h/a"]]
        script = ("import fs from 'node:fs'; import {poolAdd, poolClaim} from '" + POOL_MJS + "'; "
                  "const [file, steps] = JSON.parse(fs.readFileSync(0, 'utf8')); const KNOWN = new Set(['python-dev', 'web-dev']); let n = 0; "
                  "for (const s of steps) { const now = () => `2026-10-08T00:00:0${n++}Z`; "
                  "if (s[0] === 'add') poolAdd({ from: 'h/user', to: ['h/user'], args: s[1] }, { me: 'h/user', holder: 'h/user', file, known: KNOWN, now }); "
                  "else await poolClaim({ from: s[2], args: { id: s[1] } }, { me: 'h/user', holder: 'h/user', file, now, roleOf: async () => ({ role: 'python-dev' }) }); }")
        node_file, py_file = os.path.join(d, "node.json"), os.path.join(d, "py.json")
        r = subprocess.run(["node", "--input-type=module", "-e", script], input=json.dumps([node_file, steps]), capture_output=True, text=True, timeout=60)
        n = [0]

        def stamp():
            s = f"2026-10-08T00:00:0{n[0]}Z"
            n[0] += 1
            return s
        for s in steps:
            if s[0] == "add":
                cp.pool_add({"from": "h/user", "to": ["h/user"], "args": s[1]}, me="h/user", holder="h/user", file=py_file, known=KNOWN, now=stamp)
            else:
                cp.pool_claim({"from": s[2], "args": {"id": s[1]}}, me="h/user", holder="h/user", file=py_file, now=stamp,
                              role_of=lambda a: {"role": "python-dev"})
        node_bytes = open(node_file, "rb").read() if r.returncode == 0 else r.stderr.encode()
        check("the same adds and claim write the same bytes", open(py_file, "rb").read() == node_bytes, (node_bytes[:200], open(py_file, "rb").read()[:200]))
        cp.pool_add({"from": "h/user", "to": ["h/user"], "args": {"role": "python-dev", "title": "third"}}, me="h/user", holder="h/user",
                    file=node_file, known=KNOWN, now=lambda: "t")
        r2 = subprocess.run(["node", "--input-type=module", "-e",
                             "import fs from 'node:fs'; import {readPool} from '" + POOL_MJS + "'; process.stdout.write(JSON.stringify(readPool(fs.readFileSync(0, 'utf8'))))"],
                            input=node_file, capture_output=True, text=True, timeout=60)
        doc = json.loads(r2.stdout) if r2.returncode == 0 else {}
        check("Python continues Node's file, and Node reads what Python wrote",
              doc.get("seq") == 3 and [j["id"] for j in doc.get("jobs", [])] == ["p1", "p2", "p3"] and doc["jobs"][0]["claimed"]["by"] == "h/a",
              (doc, r2.stderr[-200:]))

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
