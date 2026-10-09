#!/usr/bin/env python3
"""Tests for tools/fabric/control/presence.py, the port of runtime/control/presence.mjs.

presence.test.mjs's cases are ported case for case, and the CLI's
contract (exit codes, stdin, the token never in argv or in an error) is
held here: agentd's functions are a stub, since agentd's port is its own.
"""
from __future__ import annotations

import io
import json
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import presence as cp  # noqa: E402


def on(role="web-dev"):
    return {"status": "ok", "online": True, "sessions": 1, "since": "2026-09-25T09:00:00.000Z", "role": role, "project": "gzapp"}


def off(role="web-dev"):
    return {"status": "ok", "online": False, "sessions": 0, "since": None, "role": role, "project": "gzapp"}


PLACED = ["h/web-dev-01", "h/web-dev-02", "h/db-admin"]


def asker(answers):
    return lambda *, expect, **kw: {a: answers.get(a) for a in expect}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    print("presence.test.mjs")
    ask = asker({"h/web-dev-01": on(), "h/web-dev-02": off()})

    def chk(to, **kw):
        return cp.check_addressees({"TO": to}, from_="h/user", token="t", placed=PLACED, ask=kw.pop("ask", ask), **kw)
    check("TO: a running session passes", chk("h/web-dev-01") == {"checked": True, "problems": [], "notes": []})
    check("...no session is offline", [(p["kind"], p["address"]) for p in chk("h/web-dev-02")["problems"]] == [("offline", "h/web-dev-02")])
    check("...no answer is unknown, never offline", [(p["kind"], p["address"]) for p in chk("h/db-admin")["problems"]] == [("silent", "h/db-admin")])
    check("...an unplaced address is said", [p["kind"] for p in chk("h/nobody")["problems"]] == ["not-placed"])

    def role_chk(answers, role="web-dev"):
        return cp.check_addressees({"TO-ROLE": role}, from_="h/user", token="t", placed=PLACED, ask=asker(answers))
    check("TO-ROLE: reached when any holder runs",
          role_chk({"h/web-dev-01": off(), "h/web-dev-02": on(), "h/db-admin": on("db-admin")}) == {"checked": True, "problems": [], "notes": []})
    none = role_chk({"h/web-dev-01": off(), "h/web-dev-02": off()})["problems"][0]
    check("...otherwise its holders, and the silent agents a holder may hide behind",
          [none["kind"], none["role"], none["holders"], none["silent"]] == ["no-holder", "web-dev", ["h/web-dev-01", "h/web-dev-02"], ["h/db-admin"]], none)
    nobody = role_chk({"h/web-dev-01": on(), "h/web-dev-02": on(), "h/db-admin": on("db-admin")}, "p2p-network-dev")["problems"][0]
    check("...a role no account holds", [nobody["kind"], nobody["holders"]] == ["no-holder", []])

    def no_ask(**kw):
        raise AssertionError("nothing to ask")
    check("a broadcast is not checked",
          cp.check_addressees({"BROADCAST": "true"}, from_="h/user", token="t", placed=PLACED, ask=no_ask) == {"checked": False})
    check("...nor a message with no addressing field", cp.check_addressees({}, from_="h/user", token="t", placed=PLACED, ask=no_ask) == {"checked": False})

    posts, reads = [], []

    def call(path, method="GET", body=None):
        if method == "POST":
            posts.append(json.loads(body))
            return {"id": "sent-1"}
        reads.append(path)
        req = json.loads(posts[0]["content"])
        return {"messages": [
            {"id": "r1", "content": json.dumps({"kind": "reply", "in_reply_to": req["id"], "from": "h/web-dev-01", "data": {"presence": on()}})},
            {"id": "r2", "content": json.dumps({"kind": "reply", "in_reply_to": "another-request", "from": "h/web-dev-02", "data": {"presence": on()}})},
            {"id": "r3", "content": json.dumps({"kind": "reply", "in_reply_to": req["id"], "from": "h/stranger", "data": {"presence": on()}})},
            {"id": "r4", "content": "not json"},
            {"id": "r5", "content": json.dumps({"kind": "reply", "in_reply_to": req["id"], "from": "h/web-dev-02", "data": {"presence": None}})}]}
    out = cp.ask_presence(from_="h/user", to=["h/web-dev-01", "h/web-dev-02"], expect=["h/web-dev-01", "h/web-dev-02"], token="t", wait_ms=300,
                          cfg={"relay_url": "x", "channel": "fabric:control", "ttl_s": 30}, call=call, new_id=lambda: "q-1", sleep=lambda s: None)
    check("askPresence: one presence request on the control channel",
          len(posts) == 1 and posts[0]["channel"] == "fabric:control" and posts[0]["sender"] == "h/user", posts)
    req = json.loads(posts[0]["content"])
    check("...a Request: kind, op, from, to", [req["kind"], req["op"], req["from"], req["to"]] == ["request", "presence", "h/user", ["h/web-dev-01", "h/web-dev-02"]])
    check("...only replies to it, from the expected, count; the rest stay null",
          out == {"h/web-dev-01": on(), "h/web-dev-02": None}, out)
    check("...the channel read at least once, from the sent id, as URLSearchParams writes it",
          reads and reads[0] == "/api/messages?channel=fabric%3Acontrol&since_id=sent-1&limit=500&full=1", reads[:1])
    check("...ttl_s outlasts the wait, the content as JSON.stringify writes it",
          req["ttl_s"] == 30 and posts[0]["content"] == json.dumps(req, separators=(",", ":"), ensure_ascii=False))
    reads.clear()
    posts.clear()
    cp.ask_presence(from_="h/user", to=["h/web-dev-01"], expect=["h/web-dev-01"], token="t", wait_ms=100,
                    cfg={"relay_url": "x", "channel": "a~b*c d", "ttl_s": 30}, call=call, new_id=lambda: "q-2", sleep=lambda s: None)
    check("...a channel name encoded as URLSearchParams encodes it (~ encoded, * not, a space as +)",
          reads and reads[0].startswith("/api/messages?channel=a%7Eb*c+d&"), reads[:1])

    failed = {"status": "failed", "error": "pgrep: spawn pgrep ENOENT", "role": "web-dev"}
    to = cp.check_addressees({"TO": "h/web-dev-01"}, from_="h/user", token="t", placed=PLACED, ask=asker({"h/web-dev-01": failed}))
    check("a reply that could not read its process table is unknown: TO",
          to["problems"] == [{"kind": "unavailable", "detail": "h/web-dev-01: pgrep: spawn pgrep ENOENT"}], to)
    role = role_chk({"h/web-dev-01": failed, "h/web-dev-02": off(), "h/db-admin": on("db-admin")})["problems"][0]
    check("...and TO-ROLE: the failed one among those that may hide a holder",
          [role["kind"], role["holders"], role["silent"]] == ["no-holder", ["h/web-dev-02"], ["h/web-dev-01"]], role)
    seen = []

    def op_ask(*, to, expect, **kw):
        seen.append({"to": to, "expect": expect})
        return {a: on("fabric-coordinator" if a == "h2/user" else "web-dev") for a in expect}
    check("an operator address may be a TO without being placed",
          cp.check_addressees({"TO": "h2/user"}, from_="h/user", token="t", placed=PLACED, operators=["h2/user"], ask=op_ask)
          == {"checked": True, "problems": [], "notes": []})
    check("...without it, unplaced",
          [p["kind"] for p in cp.check_addressees({"TO": "h2/user"}, from_="h/user", token="t", placed=PLACED, ask=op_ask)["problems"]] == ["not-placed"])
    cp.check_addressees({"TO-ROLE": "web-dev"}, from_="h/user", token="t", placed=PLACED, operators=["h2/user"], ask=op_ask)
    check("...a TO-ROLE waits only on the accounts that can hold a role", seen[-1]["expect"] == PLACED, seen[-1])

    def planning(r="web-dev"):
        return {**on(r), "planning": True}
    check("planning is a note, never a problem: TO",
          cp.check_addressees({"TO": "h/web-dev-01"}, from_="h/user", token="t", placed=PLACED, ask=asker({"h/web-dev-01": planning()}))
          == {"checked": True, "problems": [], "notes": [{"kind": "planning", "address": "h/web-dev-01"}]})
    check("...TO-ROLE: a holder that is not planning reads it now", role_chk({"h/web-dev-01": planning(), "h/web-dev-02": on()})["notes"] == [])
    check("...every running holder planning is said",
          role_chk({"h/web-dev-01": planning(), "h/web-dev-02": off(), "h/db-admin": on("db-admin")})["notes"] == [{"kind": "planning", "address": "h/web-dev-01"}])
    r = role_chk({"h/web-dev-01": planning(), "h/web-dev-02": off()})
    check("...an account that did not answer withholds the note, and planning never blocks the send", r["notes"] == [] and r["problems"] == [], r)

    print("...and as Node's checkAddressees answers, on the same inputs")
    answers = {"h/web-dev-01": on(), "h/web-dev-02": off(), "h/db-admin": {"status": "failed", "error": None, "role": "web-dev"},
               "h/x": {"status": "ok", "online": 1, "planning": 0, "role": "web-dev"},
               "h/nostatus": {"online": True}, "h/str": "x", "h/failed": {"status": "failed", "role": "web-dev"}}
    shapes = [{"TO": " h/web-dev-01 "}, {"TO": ""}, {"TO": "", "TO-ROLE": "web-dev"}, {"BROADCAST": "", "TO": "h/web-dev-02"},
              {"BROADCAST": 0, "TO-ROLE": " web-dev "}, {"TO": "h/db-admin"}, {"TO": "h/x"}, {"TO-ROLE": "db-admin"},
              {"TO": "h/web-dev-01", "TO-ROLE": "web-dev"}, {"BROADCAST": "false"}, {"TO-ROLE": ""}, {"TO": 0},
              {"TO": "\ufeffh/web-dev-01\u3000"}, {"TO-ROLE": "\u2028web-dev"}, {"TO": "h/nostatus"}, {"TO": "h/str"}, {"TO": "h/failed"}]
    placed = ["h/web-dev-01", "h/web-dev-02", "h/db-admin", "h/x", "h/nostatus", "h/str", "h/failed"]
    import subprocess
    mjs = os.path.join(HERE, "runtime", "control", "presence.mjs")
    r = subprocess.run(["node", "--input-type=module", "-e",
                        f"import fs from 'node:fs'; import {{checkAddressees}} from '{mjs}'; const i = JSON.parse(fs.readFileSync(0, 'utf8')); "
                        "const ask = async ({ expect }) => Object.fromEntries(expect.map(a => [a, a in i.answers ? i.answers[a] : null])); "
                        "const out = []; for (const m of i.shapes) out.push(await checkAddressees(m, { from: 'h/u', token: 't', placed: i.placed, ask })); "
                        "process.stdout.write(JSON.stringify(out));"],
                       input=json.dumps({"answers": answers, "shapes": shapes, "placed": placed}), capture_output=True, text=True, timeout=60)
    node = json.loads(r.stdout) if r.returncode == 0 else r.stderr[-300:]
    mine = [cp.check_addressees(m, from_="h/u", token="t", placed=placed, ask=asker(answers)) for m in shapes]
    differ = [(m, n_, g) for m, n_, g in zip(shapes, node if isinstance(node, list) else [], mine) if n_ != g]
    check(f"check_addressees answers as checkAddressees on {len(shapes)} addressings", isinstance(node, list) and not differ, differ[:3] or node)

    print("the CLI: presence.py check")
    agentd = SimpleNamespace(account_addresses=lambda: set(PLACED), operator_addresses=lambda: set(), new_id=lambda: "q",
                             control_config=lambda: {"relay_url": "x", "channel": "c", "ttl_s": 30})

    def run(argv, stdin, ask):
        o, e = io.StringIO(), io.StringIO()
        code = cp.cli(argv, io.StringIO(stdin), ask=ask, agentd=agentd, out=o, err=e)
        return code, o.getvalue(), e.getvalue()
    ok_req = json.dumps({"metadata": {"TO": "h/web-dev-01"}, "from": "h/user", "token": "SECRET-SHAPE"})
    for answer, code in (({"checked": True, "problems": [], "notes": []}, 0), ({"checked": False}, 0),
                         ({"checked": True, "problems": [{"kind": "offline"}]}, 4),
                         ({"checked": True, "problems": [{"kind": "silent"}]}, 5),
                         ({"checked": True, "problems": [{"kind": "no-holder", "silent": ["h/x"]}]}, 5),
                         ({"checked": True, "problems": [{"kind": "no-holder", "silent": []}]}, 4),
                         ({"checked": True, "problems": [{"kind": "unavailable"}, {"kind": "silent"}]}, 6)):
        got = run(["check"], ok_req, lambda *a, **k: answer)
        check(f"exit {code} for {answer.get('problems')}", got[0] == code and json.loads(got[1]) == answer, got)
    code, out, err = run(["nope"], ok_req, None)
    check("usage is exit 2", code == 2 and "usage:" in err and not out)
    for bad in ("not json", "NaN", '{"metadata": NaN, "from": "a", "token": "SECRET-SHAPE"}', "[]", '{"from": "a", "token": "t"}',
                '{"metadata": {}, "from": 5, "token": "t"}', '{"metadata": null, "from": "a", "token": "SECRET-SHAPE"}'):
        code, out, err = run(["check"], bad, lambda *a, **k: {"checked": False})
        check(f"unreadable stdin {bad[:30]!r} is exit 2, the token never quoted", code == 2 and "SECRET-SHAPE" not in err and not out, (code, err))
    code, out, err = run(["check"], json.dumps({"metadata": [], "from": "a", "token": "t"}), cp.check_addressees)
    check("metadata that is an array passes, as typeof [] is 'object', and checks nothing", code == 0 and json.loads(out) == {"checked": False}, out)

    out_bytes = io.BytesIO()
    utf8 = io.TextIOWrapper(out_bytes, encoding="utf-8")
    lone = {"checked": True, "problems": [{"kind": "offline", "address": "h/a", "presence": {"status": "ok", "online": False, "note": "\ud800"}}]}
    code = cp.cli(["check"], io.StringIO(ok_req), ask=lambda *a, **k: lone, agentd=agentd, out=utf8, err=io.StringIO())
    utf8.flush()
    check("a reply holding a lone surrogate is printed as JSON.stringify writes it, exit 4, never an encoding error",
          code == 4 and out_bytes.getvalue() == b'{"checked":true,"problems":[{"kind":"offline","address":"h/a","presence":{"status":"ok","online":false,"note":"\\ud800"}}]}\n',
          (code, out_bytes.getvalue()))
    code, out, err = run(["check"], "[" * 100000, lambda *a, **k: {"checked": False})
    check("stdin nested past any reader is exit 2, as unreadable", code == 2 and not out, (code, err))

    def deep_call(path, method="GET", body=None):
        if method == "POST":
            return {"id": "s"}
        return {"messages": [{"id": "d", "content": "[" * 100000},
                             {"id": "ok", "content": json.dumps({"kind": "reply", "in_reply_to": "q-3", "from": "h/a", "data": {"presence": on()}})}]}
    got = cp.ask_presence(from_="h/u", to=["h/a"], expect=["h/a"], wait_ms=100, cfg={"relay_url": "x", "channel": "c", "ttl_s": 30},
                          call=deep_call, new_id=lambda: "q-3", sleep=lambda s: None)
    # Unterminated: Node refuses it too. A well-formed record past Python's
    # depth is the named gap of js.json_parse, refused here, read by Node.
    check("a record nobody can read is skipped, never an abort; the rest counts", got == {"h/a": on()}, got)
    sent = []
    cp.ask_presence(from_="h/u", to=["h/a"], expect=[], wait_ms=float("inf"), cfg={"relay_url": "x", "channel": "c", "ttl_s": 30},
                    call=lambda path, method="GET", body=None: sent.append(body) or {"id": "s"}, new_id=lambda: "q", sleep=lambda s: None)
    check("an infinite wait gives ttl_s null, as JSON.stringify writes Infinity, never an overflow",
          sent and '"ttl_s":null' in json.loads(sent[0])["content"], sent)

    import subprocess
    script = os.path.join(HERE, "tools", "fabric", "control", "presence.py")
    if not os.path.exists(os.path.join(HERE, "tools", "fabric", "control", "agentd.py")):
        r = subprocess.run([sys.executable, script, "check"], input=ok_req, capture_output=True, text=True, timeout=60,
                           env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8"})
        check("before agentd's port, the script says so: exit 6, one JSON line, the token never in it",
              r.returncode == 6 and "agentd's port" in json.loads(r.stdout)["error"] and "SECRET-SHAPE" not in r.stdout + r.stderr, (r.stdout, r.stderr[-200:]))

    class Refused(Exception):
        status = 401
    code, out, _ = run(["check"], ok_req, lambda *a, **k: (_ for _ in ()).throw(Refused("/api/send -> HTTP 401\nmore")))
    check("a request that could not be made is {error, status}, exit 6", code == 6 and json.loads(out) == {"error": "/api/send -> HTTP 401", "status": 401}, out)

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
