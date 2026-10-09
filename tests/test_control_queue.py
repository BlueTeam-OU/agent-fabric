#!/usr/bin/env python3
"""Tests for tools/fabric/control/queue.py, the port of runtime/control/queue.mjs.

queue.test.mjs's cases are ported case for case. The module is unwired:
tools/fabric/jobs.py still runs queue.mjs until the cutover.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import urllib.parse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import gzcoord as cg, queue as cq  # noqa: E402

A, B = "01a11a18-4728-7d8b-afd9-0edb2d30a59c", "01a11a19-0bea-70c7-b667-1e1e5a74dbe1"
NOW = 1791461100000.0   # 2026-10-08T12:05:00Z
CFG = {"channel": "c:control", "state_channel": "s:state:control", "ttl_s": 30}


def rec(sender, waits_on, **extra):
    return {"content": json.dumps({"v": 1, "kind": "state", "from": sender, "ts": "2026-10-08T12:00:00Z", "sessions": [],
                                   **({"waits_on": waits_on} if waits_on else {}), **extra})}


def always():
    return 10 ** 9


def channel(on_request):
    """A relay with one channel: what is posted, and replies a test appends."""
    rows = []

    def call(path, method="GET", body=None):
        if method == "POST":
            b = json.loads(body)
            rows.append({"id": f"m{len(rows) + 1}", "content": b["content"]})
            sid = rows[-1]["id"]
            for reply in on_request(json.loads(b["content"])):
                rows.append({"id": f"m{len(rows) + 1}", "content": json.dumps(reply)})
            return {"id": sid}
        since = urllib.parse.parse_qs(path.split("?", 1)[1]).get("since_id", [None])[0]
        idx = next((i for i, r in enumerate(rows) if r["id"] == since), -1)
        return {"messages": rows[idx + 1:]}
    return rows, call


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    print("queue.test.mjs: waits")
    placed = {"h/b", "h/a", "h/c"}
    got = cq.waits_from([rec("h/b", [A, B]), rec("h/a", [B]), rec("h/b", [A]), rec("h/c", ["not-an-id"]), rec("x/unplaced", [B]),
                         {"content": "{broken"}, rec("h/c", [B], kind="reply")], placed, NOW)
    check("each placed account's newest record, its message ids, the waiters sorted",
          got == {"waits": {B: ["h/a"], A: ["h/b"]}, "accounts": 2, "stale": {}}, got)
    placed = {"h/a", "h/b", "h/c", "h/d"}
    got = cq.waits_from([rec("h/a", [A], ts="2026-10-08T11:00:00Z"), rec("h/b", [A]), rec("h/c", None, ts="2026-10-08T09:00:00Z"),
                         rec("h/d", [B], ts="yesterday")], placed, NOW)
    check("a stale waiter still waits, counted all the same", got["waits"] == {A: ["h/a", "h/b"], B: ["h/d"]}, got)
    check("...and is named stale with its age, or null when its ts does not parse", got["stale"] == {"h/a": 3900, "h/d": None}, got["stale"])
    check("exactly STATES_STALE_MS old is not stale", cq.waits_from([rec("h/a", [A], ts="2026-10-08T11:45:00Z")], placed, NOW)["stale"] == {})
    check("a record without waits_on waits on nothing, and replaces an older one that did",
          cq.waits_from([rec("h/a", [A]), rec("h/a", None)], {"h/a"}, NOW) == {"waits": {}, "accounts": 1, "stale": {}})
    asked = []
    got = cq.read_waits(call=lambda p: asked.append(p) or {"messages": [rec("h/a", [A])]}, cfg=CFG, placed={"h/a"})
    check("readWaits reads the state channel, never the control channel", "channel=s%3Astate%3Acontrol" in asked[0] and got["waits"] == {A: ["h/a"]})

    print("queue.test.mjs: askHolder")
    sent = {}

    def replies(req):
        sent.update(req)
        return [{"v": 1, "kind": "reply", "in_reply_to": req["id"], "from": "h/forger", "op": req["op"], "data": {"pool-claim": {"status": "claimed", "job": {"id": "p1"}}}},
                {"v": 1, "kind": "reply", "in_reply_to": "other", "from": "h/user", "op": req["op"], "data": {"pool-claim": {"status": "claimed"}}},
                {"v": 1, "kind": "reply", "in_reply_to": req["id"], "from": "h/user", "op": req["op"], "data": {"pool-claim": {"status": "refused", "reason": "no"}}}]
    _, call = channel(replies)
    got = cq.ask_holder(call=call, cfg=CFG, from_="h/py", holder="h/user", op="pool-claim", args={"id": "p1"}, new_id=lambda: "q1",
                        wait_ms=2000, left=always, sleep=lambda s: None)
    check("only the holder's reply to this request counts; a forged one is skipped", got == {"status": "refused", "reason": "no"}, got)
    check("...the request: to the holder, from the asker, the args, a request of the op",
          [sent["to"], sent["from"], sent["args"], sent["kind"], sent["op"]] == [["h/user"], "h/py", {"id": "p1"}, "request", "pool-claim"])
    check("...it lives as long as the asker waits, not the channel's 30 s", sent["ttl_s"] == 2)
    posted = []

    def failing(path, method="GET", body=None):
        if method == "POST":
            posted.append(1)
            return {"id": "m1"}
        raise cg.ApiError("down", status=502)
    try:
        cq.ask_holder(call=failing, cfg=CFG, from_="h/py", holder="h/user", op="pool-claim", args={"id": "p1"}, new_id=lambda: "q",
                      wait_ms=500, left=always, sleep=lambda s: None)
        check("a relay that fails after the post says it was sent", False)
    except cg.ApiError as e:
        check("a relay that fails after the post says it was sent", getattr(e, "sent", None) is True and e.status == 502 and posted)

    def refused(path, method="GET", body=None):
        raise cg.ApiError("no", status=403)
    try:
        cq.ask_holder(call=refused, cfg=CFG, from_="h/py", holder="h/user", op="pool-claim", args={"id": "p1"}, new_id=lambda: "q",
                      wait_ms=500, left=always, sleep=lambda s: None)
        check("...a post refused says nothing of sent", False)
    except cg.ApiError as e:
        check("...a post refused says nothing of sent", not hasattr(e, "sent"))
    _, quiet = channel(lambda req: [])
    clock = [0.0]

    def tick(s):
        clock[0] += s * 1000
    check("a holder that does not answer is None, never an answer",
          cq.ask_holder(call=quiet, cfg=CFG, from_="h/py", holder="h/user", op="pool-list", args={"role": "python-dev"}, new_id=lambda: "q",
                        wait_ms=500, left=always, sleep=tick, clock=lambda: clock[0]) is None)

    print("queue.test.mjs: who is placed")
    with tempfile.TemporaryDirectory() as d:
        reg = os.path.join(d, "registry.json")
        for label, text, said in (("no registry", None, "cannot be read"), ("not JSON", "{broken", "cannot be read"), ("no placement", "{}", "no placement")):
            if text is not None:
                with open(reg, "w") as fh:
                    fh.write(text)
            try:
                cq.placed_accounts(reg)
                check(f"{label}: an error, never nobody", False)
            except cq.Unreadable as e:
                check(f"{label}: an error, never nobody", said in str(e), str(e))
        with open(reg, "w") as fh:
            json.dump({"placement": {"a": "h", "b": "k"}}, fh)
        check("the placed addresses", cq.placed_accounts(reg) == {"h/a", "k/b"})

    print("queue.test.mjs: unsent")
    check("a 403: certainly unsent", cq.unsent(cg.ApiError("x", status=403)) is True)
    check("a connection refused: certainly unsent", cq.unsent(cg.ApiError("x", connection_refused=True)) is True)
    check("a 5xx may come after the write", cq.unsent(cg.ApiError("x", status=502)) is False)
    check("a reset may come after the write", cq.unsent(cg.ApiError("x")) is False)
    check("a plain error", cq.unsent(ValueError("x")) is False)
    check("a timed-out post may have been stored", cq.unsent(cg.ApiError("/api/send -> no answer within 30 s", timed_out=True)) is False)

    print("queue.test.mjs: the run's budget")
    with open(os.path.join(HERE, "tools", "fabric", "jobs.py"), encoding="utf-8") as fh:
        m = re.search(r"^QUEUE_TIMEOUT_S = (\d+)$", fh.read(), re.M)
    outer = int(m.group(1)) if m else 0
    check("one budget under jobs.py's kill, with room to start", outer > 0 and cq.QUEUE_BUDGET_MS <= outer * 1000 - 5000 and cq.QUEUE_CALL_TIMEOUT_MS <= cq.QUEUE_BUDGET_MS)
    seen = []

    def fake(tok, path, **kw):
        seen.append(kw)
    cq.bound_call("tok", {"relay_url": "http://r"}, fake, always)("/api/send", method="POST")
    cq.bound_call("tok", {"relay_url": "http://r"}, fake, lambda: 3000)("/x")
    check("every call takes at most what is left", [k["timeout_s"] for k in seen] == [cq.QUEUE_CALL_TIMEOUT_MS / 1000, 3.0], seen)
    check("...with the relay and the method", seen[0] == {"relay_url": "http://r", "method": "POST", "body": None, "timeout_s": 15.0}, seen[0])
    check("the budget is whole milliseconds", isinstance(cq.budget_left(), int))
    try:
        cq.bound_call("tok", {"relay_url": "http://r"}, fake, lambda: 0)("/api/send?x=1", method="POST")
        check("a spent budget asks nothing", False)
    except cq.BudgetSpent as e:
        check("a spent budget asks nothing, certainly unsent, said as the budget",
              cq.unsent(e) and cq.relay_error(e, {"relay_url": "http://r"}) == "/api/send: not asked, this run's 25 s budget is spent" and len(seen) == 2, str(e))
    with tempfile.TemporaryDirectory() as home:
        saved = {k: os.environ.get(k) for k in ("HOME", "CLAUDE_BRIDGE_AUTH_TOKEN")}
        os.environ.update({"HOME": home, "CLAUDE_BRIDGE_AUTH_TOKEN": "env-tok"})
        try:
            seen2 = []
            r = cq.relay({"agent": "x", "project": None}, {"relay_url": "http://r"}, call=lambda tok, p, **kw: seen2.append((tok, p, kw)), left=lambda: 4000)
            r["call"]("/api/messages?x=1")
            check("relay() itself: through the bound, with the token it resolved",
                  seen2 == [("env-tok", "/api/messages?x=1", {"relay_url": "http://r", "method": "GET", "body": None, "timeout_s": 4.0})], seen2)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    asked2 = []

    def counted(path, method="GET", body=None):
        asked2.append(json.loads(json.loads(body)["content"]) if method == "POST" else "GET")
        return {"id": "m1"} if method == "POST" else {"messages": []}
    left = [1200]
    clock = [0.0]
    check("the wait is the run's budget when shorter", cq.ask_holder(call=counted, cfg=CFG, from_="h/py", holder="h/user", op="pool-list",
                                                                    args={"role": "python-dev"}, new_id=lambda: "q", wait_ms=10000, left=lambda: left[0],
                                                                    sleep=tick, clock=lambda: clock[0]) is None)
    check("...and the request lives no longer", asked2[0]["ttl_s"] == 2, asked2[0])
    asked2.clear()
    left[0] = 0
    try:
        cq.ask_holder(call=counted, cfg=CFG, from_="h/py", holder="h/user", op="pool-list", args={"role": "python-dev"}, new_id=lambda: "q",
                      wait_ms=5000, left=lambda: left[0])
        check("spent before the post: nothing posted", False)
    except cq.BudgetSpent as e:
        check("spent before the post: nothing posted, said as the budget, unsent", cq.unsent(e) and asked2 == [])

    print("the CLI: argv, stdout, exits (queue.mjs's header)")
    from types import SimpleNamespace
    agentd = SimpleNamespace(control_config=lambda: {"relay_url": "http://r", **CFG}, new_id=lambda: "q9")
    with tempfile.TemporaryDirectory() as d:
        reg = os.path.join(d, "registry.json")
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h": {"operator": "user"}}, "placement": {"a": "h", "py": "h"}}, fh)
        saved = {k: os.environ.get(k) for k in ("HOME", "CLAUDE_BRIDGE_AUTH_TOKEN")}

        def run(argv, call=None, token="tok", who=None, wait_ms=300):
            lines, errs = [], []
            os.environ["HOME"] = d
            if token:
                os.environ["CLAUDE_BRIDGE_AUTH_TOKEN"] = token
            else:
                os.environ.pop("CLAUDE_BRIDGE_AUTH_TOKEN", None)
            code = cq.cli(argv, out=lines.append, err=errs.append, agentd=agentd, who=who or {"agent": "py", "host": "h", "role": "python-dev", "project": None},
                          call=call or (lambda tok, p, **kw: {"messages": []}), registry=reg, wait_ms=wait_ms)
            return code, [json.loads(x) for x in lines], errs
        try:
            for bad in ([], ["nope"], ["waits", "x"], ["pool-claim", "../p1"], ["pool-list", "Bad"], ["pool-claim", "p1", "extra"]):
                code, out, errs = run(bad)
                check(f"usage {bad}: exit 2, nothing on stdout", code == 2 and not out and errs and errs[0].startswith("usage:"))
            code, out, _ = run(["waits"], token=None)
            check("no token: exit 3, sent false", code == 3 and out == [{"error": "no CLAUDE_BRIDGE_AUTH_TOKEN (fabric-secrets sync)", "sent": False}], out)
            code, out, _ = run(["waits"], call=lambda tok, p, **kw: {"messages": [rec("h/a", [A])]})
            check("waits: exit 0, the waits of the placed (its old record named stale, by the real clock)",
                  code == 0 and out[0]["waits"] == {A: ["h/a"]} and out[0]["accounts"] == 1 and list(out[0]["stale"]) == ["h/a"], out)
            code, out, _ = run(["pool-list"], who={"agent": "py", "host": "h", "role": None, "project": None})
            check("pool-list with no bound role: exit 4, sent false", code == 4 and out[0]["sent"] is False and "no bound role" in out[0]["error"], out)
            code, out, _ = run(["pool-list"])
            check("a holder that does not answer: exit 3, sent true", code == 3 and out[0]["sent"] is True and out[0]["holder"] == "h/user"
                  and "did not answer within" in out[0]["error"], out)

            def holder_answers(tok, p, method="GET", body=None, **kw):
                if method == "POST":
                    return {"id": "m1"}
                return {"messages": [{"id": "m2", "content": json.dumps({"v": 1, "kind": "reply", "in_reply_to": "q9", "from": "h/user",
                                                                         "data": {"pool-claim": {"status": "claimed", "job": {"id": "p1"}}}})}]}
            code, out, _ = run(["pool-claim", "p1"], call=holder_answers)
            check("pool-claim answered: exit 0, the holder and its answer",
                  code == 0 and out == [{"holder": "h/user", "answer": {"status": "claimed", "job": {"id": "p1"}}}], out)
            with open(reg, "w") as fh:
                json.dump({"hosts": {"h": {}, "k": {}}, "placement": {}}, fh)
            code, out, _ = run(["pool-claim", "p1"])
            check("no holder: exit 4, sent false", code == 4 and out[0]["sent"] is False and "no account holds the pool" in out[0]["error"], out)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    print("the script itself, as jobs.py would run it")
    import subprocess
    script = os.path.join(HERE, "tools", "fabric", "control", "queue.py")
    agentd_here = os.path.exists(os.path.join(HERE, "tools", "fabric", "control", "agentd.py"))
    with tempfile.TemporaryDirectory() as home:
        r = subprocess.run([sys.executable, script, "waits"], capture_output=True, text=True, timeout=60,
                           env={"PATH": os.environ.get("PATH", ""), "HOME": home, "LANG": "C.UTF-8"})
    if agentd_here:
        check("with agentd's port in the tree, the script runs (no token here: exit 3, sent false)",
              r.returncode == 3 and json.loads(r.stdout).get("sent") is False, (r.returncode, r.stdout, r.stderr[-300:]))
    else:
        check("before agentd's port, the script says so: exit 3, sent false, never an import traceback",
              r.returncode == 3 and json.loads(r.stdout) == {"error": "the CLI needs tools/fabric/control/agentd.py (control_config, new_id), "
                                                                   "agentd's port, which is not in this tree yet", "sent": False}, (r.stdout, r.stderr[-300:]))
    # As a script runs: its directory first on sys.path. After the module ran,
    # `import queue` must find the standard library's, not this file.
    probe = subprocess.run([sys.executable, "-c", f"import sys, runpy; sys.path[0] = {os.path.dirname(script)!r}; sys.argv = ['queue.py', 'nope'];"
                            f" runpy.run_path({script!r}, run_name='probe'); import queue as q; print(q.__file__)"],
                           capture_output=True, text=True, timeout=60)
    check("run as a script, its directory no longer shadows the standard library's queue",
          probe.returncode == 0 and probe.stdout.strip() and "tools/fabric/control" not in probe.stdout, (probe.stdout, probe.stderr[-300:]))
    for name in ("gzcoord", "jobs", "pool", "presence", "sessions"):
        other = os.path.join(os.path.dirname(script), f"{name}.py")
        probe = subprocess.run([sys.executable, "-c", f"import sys, runpy; sys.path[0] = {os.path.dirname(other)!r}; sys.argv = [{name + '.py'!r}];"
                                f" runpy.run_path({other!r}, run_name='probe'); import queue as q; print(q.__file__)"],
                               capture_output=True, text=True, timeout=60)
        check(f"run as a script, {name}.py's directory never shadows the standard library's queue either",
              probe.returncode == 0 and probe.stdout.strip() and "tools/fabric/control" not in probe.stdout, (probe.stdout, probe.stderr[-300:]))
    # An agentd.py that is there but fails its own import is a defect, said
    # as it is, never "not in this tree yet": a scratch copy of tools/fabric.
    import shutil
    with tempfile.TemporaryDirectory() as tmp:
        fabric = os.path.join(tmp, "fabric")
        shutil.copytree(os.path.join(HERE, "tools", "fabric"), fabric, ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(fabric, "control", "agentd.py"), "w", encoding="utf-8") as fh:
            fh.write("import control_agentd_missing_dependency\n")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        r = subprocess.run([sys.executable, os.path.join(fabric, "control", "queue.py"), "waits"], capture_output=True, text=True, timeout=60, env=env)
        check("an agentd.py that fails its import is said as its own error, never as agentd's port missing",
              r.returncode == 3 and "control_agentd_missing_dependency" in r.stdout and "not in this tree yet" not in r.stdout, (r.stdout, r.stderr[-300:]))
        req = json.dumps({"metadata": {}, "from": "h/u", "token": "t"})
        r = subprocess.run([sys.executable, os.path.join(fabric, "control", "presence.py"), "check"], input=req, capture_output=True, text=True,
                           timeout=60, env=env)
        check("presence: an agentd.py that fails its import is its own {error} line, never agentd's port missing",
              r.returncode == 6 and "control_agentd_missing_dependency" in json.loads(r.stdout)["error"] and "not in this tree yet" not in r.stdout,
              (r.returncode, r.stdout, r.stderr[-300:]))

    print("queue.test.mjs: relayError")
    c = {"relay_url": "http://r"}
    check("no answer", cq.relay_error(cg.ApiError("/api/send -> no answer within 30 s", timed_out=True), c) == "the relay at http://r did not answer (no answer within 30 s)")
    check("refused", cq.relay_error(cg.ApiError("x", status=401), c) == "the relay refused (HTTP 401)")
    check("unreachable", cq.relay_error(ValueError("x"), c) == "the relay is unreachable at http://r")

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
