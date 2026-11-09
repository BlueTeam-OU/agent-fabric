#!/usr/bin/env python3
"""The public read `job-state` and what a non-operator's blockers do with it (tools/fabric/control/jobs.py job_state,
control/queue.py job-state, tools/fabric/jobsparts/blockers.py). Three sides:

  the answering side   a placed account asks one account about exactly one job; only the sender of the request the job was
                       taken from is answered, with an id and a state and nothing else;
  the asking side      queue.py: an operator is told to read the board, anyone else asks the target's control agent;
  the blockers         job: and request: use the answer for a caller that is no operator, the board for one that is, and a
                       re-point that would make a cycle is refused.

Plain script: prints ok/FAIL, exit 1 on any failure. tests/test_jobs_blockers.py and test_jobs_request_repoint.py (the
board path, a fake fabric-ctl) run unchanged beside it."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, this script's own directory

own_instance_tree()
from control import agentd, jobs as cj, ops, queue as cq  # noqa: E402

ME = "h/me"                 # the asker: a placed login, no operator
USER = "h/user"             # the host operator
MID = "01a1b000-0000-7000-8000-000000000001"
OTHER_MID = "01a1b000-0000-7000-8000-000000000002"


def listing(*jobs: dict) -> list[dict]:
    return list(jobs)


def job(i: str, state: str, title: str, sender: str | None = ME) -> dict:
    return {"id": i, "state": state, "title": title, "source": {"kind": "request", "from": sender} if sender else {"kind": "self"}}


def runner(jobs: list[dict], calls: list | None = None, code: int = 0):
    def run(argv, **kw):
        if calls is not None:
            calls.append(argv)
        return SimpleNamespace(stdout=json.dumps(jobs), stderr="boom\n" if code else "", returncode=code)
    return run


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:500]}"))
        fails += not good

    board = listing(job("j1", "delivered", "the wanted one (REQUEST " + MID.upper() + ")"),
                    job("j2", "active", "somebody else's secret title", sender="h/other"),
                    job("j3", "done", "closed work (REQUEST " + OTHER_MID + ")"),
                    job("j4", "queued", "own work", sender=None),
                    {**job("j5", "queued", "from a pool"), "source": {"kind": "pool", "from": ME}})

    def ask(args, sender=ME, jobs=board, calls=None, code=0):
        return cj.job_state({"id": "q", "op": "job-state", "from": sender, "args": args}, home="/h", root="/r", run=runner(jobs, calls, code))

    print("the answering side")
    got = ask({"job": "j1"})
    check("the sender is told the state of the job its request became, and only id and state", got == {"status": "ok", "id": "j1", "state": "delivered"}, got)
    calls: list = []
    got = ask({"job": "j3"}, calls=calls)
    check("a job that is done is still told (the list is read with --all)", got == {"status": "ok", "id": "j3", "state": "done"} and "--all" in calls[0], (got, calls))
    got = ask({"request": MID})
    check("a message id names the job whose title ends (REQUEST <id>), the id folded to lower case",
          got == {"status": "ok", "id": "j1", "state": "delivered"}, got)
    check("…whichever case the asker writes it in", ask({"request": MID.upper()}) == got)
    got = ask({"job": "j2"})
    check("an asker that is not the sender is refused", got["status"] == "refused" and set(got) == {"status", "reason"}, got)
    check("the refusal names no title, no id and no state", all(w not in json.dumps(got) for w in ("secret", "j2", "active")), got)
    check("the refusal is the same for every job that exists (an own job, with no sender, is one)",
          ask({"job": "j4"}) == got and ask({"job": "j2"}, sender="h/user") == got, ask({"job": "j4"}))
    check("a pool job whose `from` is the asker is not answered: only a request's sender is", ask({"job": "j5"})["status"] == "refused")
    check("a sender is not the sender of another job: j1 is refused to anyone else", ask({"job": "j1"}, sender="h/other")["status"] == "refused")
    check("a job the list does not hold is absent", ask({"job": "j9"}) == {"status": "ok", "id": "j9", "state": "absent"})
    check("a message id no job carries is absent", ask({"request": "01a1b000-0000-7000-8000-0000000000ff"})["state"] == "absent")
    check("no field of the other jobs is in any answer", all("title" not in ask({"job": i}) and "j2" not in json.dumps(ask({"request": MID})) for i in ("j1", "j3")))
    for bad in ({}, {"job": "j1", "request": MID}, {"job": "../j1"}, {"job": 1}, {"request": "x"}, {"jobs": "j1"}, None, ["j1"]):
        check(f"args {bad!r}: refused, nothing run", ask(bad, calls=(c := []))["status"] == "refused" and not c)
    got = ask({"job": "j1"}, code=1)
    check("a list that cannot be read is refused, never absent", got["status"] == "refused", got)
    check("a request with no `from` is refused", cj.job_state({"args": {"job": "j1"}}, home="/h", root="/r", run=runner(board))["status"] == "refused")

    print("who is answered")
    check("job-state is public: any placed account may ask", "job-state" in ops.PUBLIC_OPS and "job-state" in ops.OPS)
    accounts = {"h/me", "h/other"}
    seen: set = set()
    me = {"address": "h/target"}
    rec = {"content": json.dumps({"v": 1, "kind": "request", "id": "r1", "from": ME, "to": ["h/target"], "op": "job-state", "ts": agentd.js.iso_now(),
                                  "ttl_s": 60, "args": {"job": "j1"}})}
    check("agentd accepts it from a placed account that is no operator", agentd.accept(rec, me=me, operators={USER}, accounts=accounts, ttl_s=60, seen=seen)["ok"])
    forged = {"content": json.dumps({**json.loads(rec["content"]), "id": "r2", "from": "h/stranger"})}
    check("…and not from one that is not placed", not agentd.accept(forged, me=me, operators={USER}, accounts=accounts, ttl_s=60, seen=seen)["ok"])
    check("…and `jobs` stays an operator's", not agentd.accept({"content": json.dumps({**json.loads(rec["content"]), "id": "r3", "op": "jobs"})},
                                                                  me=me, operators={USER}, accounts=accounts, ttl_s=60, seen=seen)["ok"])
    reply = agentd.answer({"id": "r1", "op": "job-state", "from": ME, "to": ["h/target"], "args": {"job": "j1"}},
                          {"me": me, "started": agentd.js.iso_now(), "home": "/h", "root": "/r", "jobs_opts": {"run": runner(board)}})
    check("agentd answers it as data['job-state']", reply["data"]["job-state"] == {"status": "ok", "id": "j1", "state": "delivered"}, reply)

    print("the asking side (queue.py job-state)")
    fake_agentd = SimpleNamespace(control_config=lambda: {"relay_url": "http://r", "channel": "c:control", "state_channel": "s", "ttl_s": 30},
                                  new_id=lambda: "q9", operator_addresses=lambda reg=None: agentd.operator_addresses(reg))
    saved = {k: os.environ.get(k) for k in ("HOME", "CLAUDE_BRIDGE_AUTH_TOKEN", "AGENT_FABRIC_ROOT")}
    cwd0 = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        reg = os.path.join(d, "registry.json")

        def registry(doc=None):
            with open(reg, "w") as fh:
                json.dump(doc or {"hosts": {"h": {"operator": "user"}}, "placement": {"user": "h", "me": "h", "target": "h"}}, fh)

        registry()

        def run(argv, login="me", call=None):
            lines, errs, posted = [], [], []
            os.environ.update(HOME=d, CLAUDE_BRIDGE_AUTH_TOKEN="tok", AGENT_FABRIC_ROOT=os.path.join(d, "empty-ws", "fabric"))
            os.chdir(d)

            def relay(tok, p, method="GET", body=None, **kw):
                if method == "POST":
                    posted.append(json.loads(json.loads(body)["content"]))
                    return {"id": "m1"}
                return {"messages": [{"id": "m2", "content": json.dumps({"v": 1, "kind": "reply", "in_reply_to": "q9", "from": "h/target",
                                                                         "data": {"job-state": {"status": "ok", "id": "j1", "state": "delivered"}}})}]}
            code = cq.cli(argv, out=lines.append, err=errs.append, agentd=fake_agentd, who={"agent": login, "host": "h", "role": "python-dev", "project": None},
                          call=call or relay, registry=reg, wait_ms=300)
            return code, [json.loads(x) for x in lines], errs, posted
        try:
            code, out, _, posted = run(["job-state", "target", "j1"])
            check("a non-operator asks the target's control agent, by its address, for exactly that job",
                  code == 0 and out == [{"target": "h/target", "answer": {"status": "ok", "id": "j1", "state": "delivered"}}]
                  and len(posted) == 1 and posted[0]["to"] == ["h/target"] and posted[0]["from"] == "h/me" and posted[0]["op"] == "job-state"
                  and posted[0]["args"] == {"job": "j1"}, (code, out, posted))
            code, out, _, posted = run(["job-state", "target", MID.upper()])
            check("a message id goes as {request}, folded to lower case", posted and posted[0]["args"] == {"request": MID}, posted)
            code, out, _, posted = run(["job-state", "target", "j1"], login="user")
            check("an operator is told so and nothing is posted (it reads the board)", code == 0 and out == [{"operator": True}] and not posted, (out, posted))
            code, out, _, posted = run(["job-state", "nobody", "j1"])
            check("a login that is not placed: exit 4, nothing posted", code == 4 and out[0]["sent"] is False and not posted, (code, out))
            code, out, _, posted = run(["job-state", "target", "j1"], login="stranger")
            check("an asker that is not placed: exit 4, nothing posted", code == 4 and not posted, (code, out))
            for bad in ([], ["x"], ["target"], ["target", "j0"], ["Target", "j1"], ["target", "j1", "x"], ["target", "../j1"]):
                code, out, errs, posted = run(["job-state", *bad])
                check(f"usage {bad}: exit 2, nothing on stdout or posted", code == 2 and not out and not posted and errs, (code, out))
            with open(reg, "w") as fh:
                fh.write("{")
            code, out, _, posted = run(["job-state", "target", "j1"])
            check("a registry that cannot be read is exit 3, sent false, never `not an operator`", code == 3 and out[0]["sent"] is False and not posted, (code, out))
            registry()
            code, out, _, _ = run(["job-state", "target", "j1"], call=lambda tok, p, method="GET", body=None, **kw: {"id": "m1"} if method == "POST" else {"messages": []})
            check("a target that does not answer: exit 3, sent true", code == 3 and out[0]["sent"] is True, (code, out))
        finally:
            os.chdir(cwd0)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    print("the blockers")
    spec = importlib.util.spec_from_file_location("jobs_state", os.path.join(HERE, "tools", "fabric", "jobs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    bl = mod.blockers

    def patched(asked: dict | list, boards: dict | None = None):
        """bl with ask_queue answering `asked` (a dict, or a function of the argv) and read_board answering `boards`; (calls, restore)."""
        calls: list = []
        orig = bl.ask_queue, bl.read_board

        def fake_ask(*argv):
            calls.append(("ask", *argv))
            got = asked(*argv) if callable(asked) else asked
            if isinstance(got, Exception):
                raise got
            return got

        def fake_board(login):
            calls.append(("board", login))
            return (boards or {}).get(login, (None, "fabric-ctl: not an operator"))
        bl.ask_queue, bl.read_board = fake_ask, fake_board
        return calls, lambda: setattr(bl, "ask_queue", orig[0]) or setattr(bl, "read_board", orig[1])

    def answer(state, ident="j1", status="ok", reason=None):
        return {"target": "h/peer", "answer": {"status": status, **({"id": ident, "state": state} if status == "ok" else {"reason": reason})}}

    def job_check(said, seen=False, boards=None):
        calls, restore = patched(said, boards)
        try:
            return bl.check_job("peer", "j1", seen), calls
        finally:
            restore()

    (res, seen_now), calls = job_check(answer("delivered"))
    check("a non-operator clears a job: blocker on a delivered peer job", res.state == "cleared" and res.detail == "delivered" and seen_now, res)
    check("…through the public op, never the board", calls == [("ask", "job-state", "peer", "j1")], calls)
    (res, _), _ = job_check(answer("active"))
    check("a peer job that is still active waits", (res.state, res.detail) == ("waiting", "active"), res)
    (res, _), _ = job_check(answer("done"))
    check("a done job clears though it was never seen open (the op reads --all: it was there)", res.state == "cleared", res)
    (res, _), _ = job_check(answer("dropped"))
    check("a dropped job clears", res.state == "cleared", res)
    (res, _), _ = job_check(answer("absent"))
    check("a job the list does not hold, never seen, is unknown, not cleared", res.state == "unknown", res)
    (res, _), _ = job_check(answer("absent"), seen=True)
    check("…and cleared when it was seen open before", res.state == "cleared", res)
    (res, _), _ = job_check(answer(None, status="refused", reason="job-state answers the sender of the request the job was taken from"))
    check("a refusal is unknown, with the refusal's words", res.state == "unknown" and "answers the sender" in res.detail, res)
    (res, _), _ = job_check({"target": "h/peer", "answer": {"status": "ok", "id": "j7", "state": "delivered"}})
    check("an answer about another job than the one asked is unknown, never cleared", res.state == "unknown", res)
    (res, _), _ = job_check({"target": "h/peer", "answer": {"status": "ok", "id": "j1", "state": "bogus"}})
    check("a state that is none of the job states is unknown", res.state == "unknown", res)
    (res, _), calls = job_check({"operator": True}, boards={"peer": ([{"id": "j1", "state": "delivered"}], "")})
    check("an operator reads the board, as before", res.state == "cleared" and calls[-1] == ("board", "peer"), (res, calls))
    (res, _), calls = job_check(bl.Unreachable("no answer within 30 s"), boards={"peer": ([{"id": "j1", "state": "delivered"}], "")})
    check("when the op cannot be asked at all, the board is read as before", res.state == "cleared" and calls[-1] == ("board", "peer"), (res, calls))
    (res, _), _ = job_check(bl.Unreachable("no answer within 30 s"))
    check("…and a board that refuses too is unknown with its words", res.state == "unknown" and "not an operator" in res.detail, res)

    print("a request: re-points to the job whose title carries its id")
    def became(said, body="", boards=None, decision=False):
        calls, restore = patched(said, boards)
        try:
            return bl._became(MID, "peer", body, decision), calls
        finally:
            restore()

    body = "taken as job:peer/j95; see also j103"
    (got, _, _, _), calls = became(answer("active", "j103"), body)
    check("the job the control agent names, not the one the body names", got == "job:peer/j103", got)
    check("…asked by the message id", calls == [("ask", "job-state", "peer", MID)], calls)
    (got, was_seen, why, _), _ = became(answer("absent", None), "job:peer/j95")
    check("no job carries the id: the wait is over, the body is not read", got is None and why is None and not was_seen, (got, why))
    (got, _, why, _), _ = became(answer(None, status="refused", reason="no"), "taken as j95")
    check("a refusal is a board that cannot be read: the one job the body names is taken, unseen", got == "job:peer/j95" and why and "refused" in why, (got, why))
    rows2 = [{"id": "j95", "state": "active", "title": "y", "blockers": [{}, {"spec": "job:me/j306"}, "pr:o/r#1", 3]}]
    (got, _, _, peer), _ = became({"operator": True}, "taken as j95", boards={"peer": (rows2, "")})
    check("a body-named job found on a readable board carries its blockers, a malformed one is skipped", got == "job:peer/j95" and peer == ["job:me/j306", "pr:o/r#1"], (got, peer))
    (got, _, why, _), _ = became(answer(None, status="refused", reason="no"), "j95 and j96")
    check("a body that names two jobs of the sender stays unknown", got is None and why, (got, why))
    (got, _, why, _), _ = became(answer(None, status="refused", reason="no"), "j95", decision=True)
    check("a DECISION settles it: no body token", got is None and why is None, (got, why))
    rows = [{"id": "j103", "state": "active", "title": f"x (REQUEST {MID})", "blockers": [{"spec": "job:me/j306"}]}, {"id": "j95", "state": "active", "title": "y"}]
    (got, was_seen, _, peer), calls = became({"operator": True}, body, boards={"peer": (rows, "")})
    check("an operator still reads the board, which is authoritative over the body", got == "job:peer/j103" and was_seen and peer == ["job:me/j306"], (got, peer))

    print("a cycle is refused")
    orig_identity = (bl.identity.current_agent, bl.identity.read_jobs)
    mine = {"jobs": [{"id": "j306", "state": "blocked", "blockers": [f"request:{MID}"]}, {"id": "j307", "state": "blocked", "blockers": ["job:me/j306"]},
                     {"id": "j308", "state": "blocked", "blockers": ["job:me/j307"]}]}
    bl.identity.current_agent, bl.identity.read_jobs = (lambda: "me"), (lambda agent=None: mine)
    try:
        check("the peer job waits on my job that holds this request: refused", bl._cycle("job:peer/j95", MID, ["job:me/j306"]) == "job:me/j306")
        check("a control: it waits on something else, or nothing", bl._cycle("job:peer/j95", MID, ["job:me/j999", "pr:o/r#1"]) is None
              and bl._cycle("job:peer/j95", MID, []) is None)
        check("a job of this list that waits on the holder, two hops away, is a cycle too", bl._cycle("job:me/j308", MID, []) == "job:me/j306")
        check("the holder itself as the target is a cycle", bl._cycle("job:me/j306", MID, []) == "job:me/j306")
        check("a control: another job of this list that does not lead to the holder", bl._cycle("job:me/j999", MID, []) is None)
    finally:
        bl.identity.current_agent, bl.identity.read_jobs = orig_identity

    # check_request end to end over the journal: the blocker is not re-pointed, the check says why.
    with tempfile.TemporaryDirectory() as tmp:
        store = os.path.join(tmp, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as fh:
            fh.write("01a0f782-7e06-7dee-811f-0a860ed93bf3\n")
        os.makedirs(os.path.join(tmp, "home"))
        os.environ.update(AGENT_FABRIC_SECRET_STORE=store, HOME=os.path.join(tmp, "home"))
        os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state")
        os.makedirs(os.environ["AGENT_FABRIC_STATE_DIR"])
        import subprocess
        reply = (f"[GZCOORD/1] REPLY\nFROM: h/peer\nROLE: x\nTO: h/me\nIN-REPLY-TO: {MID}\nMESSAGE-ID: 01a1b000-0000-7000-8000-0000000000aa\n"
                 "SUBJECT: s\n\nREPLY:\ntaken\n")
        subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "episodic.py"), "gzcoord-in"], env={**os.environ},
                       input=json.dumps({"content": reply, "seq": 1}) + "\n", capture_output=True, text=True, timeout=60, check=True)
        bl.identity.current_agent, bl.identity.read_jobs = (lambda: "me"), (lambda agent=None: mine)
        try:
            for peer_waits, label in ((["job:me/j306"], "refused and said, no job to re-point to"), ([], "re-pointed when nothing waits on the holder (the control)")):
                rows = [{"id": "j95", "state": "active", "title": f"x (REQUEST {MID})", "blockers": [{"spec": s} for s in peer_waits]}]
                calls, restore = patched({"operator": True}, boards={"peer": (rows, "")})
                try:
                    res = bl.check_request(MID)
                finally:
                    restore()
                if peer_waits:
                    check(f"check_request: {label}", res.state == "unknown" and res.became is None and "cycle" in res.detail, res)
                else:
                    check(f"check_request: {label}", res.state == "waiting" and res.became == "job:peer/j95", res)
        finally:
            bl.identity.current_agent, bl.identity.read_jobs = orig_identity
            for k in ("AGENT_FABRIC_STATE_DIR", "AGENT_FABRIC_SECRET_STORE"):
                os.environ.pop(k, None)
            if saved["HOME"] is None:     # a runner with no HOME: absent again, not the string "None"
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = saved["HOME"]

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
