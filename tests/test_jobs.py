#!/usr/bin/env python3
"""bin/fabric-jobs (tools/fabric/jobs.py): the job list, through the real
command and a scratch state directory — never the login's own list."""
from __future__ import annotations

import datetime
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "bin", "fabric-jobs")


def message(kind: str, to: str, mid: str, subject: str, project: str = "fixture") -> str:
    return (f"[GZCOORD/1] {kind}\nFROM: other-host/sender\nROLE: backend-dev\nPROJECT: {project}\n{to}\n"
            f"MESSAGE-ID: 01a09fc1-0000-7000-8000-00000000000{mid}\nSUBJECT: {subject}\n\nREQUEST:\nplease\n")


def fake_relay(records: list[dict], state: list[dict] | None = None) -> http.server.HTTPServer:
    """The relay's history: `records` on every channel but the state
    channel, which serves `state` (the control plane's state records)."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            on_state = "channel=t%3Astate%3Acontrol" in self.path
            rows = (state or []) if on_state else records
            body = json.dumps({"messages": rows} if self.path.startswith("/api/messages") else {"ok": True}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def fake_holder(answer) -> http.server.HTTPServer:
    """A relay whose control channel has a pool holder behind it: each
    request posted there gets `answer(request)` as the reply's data[op],
    from the request's `to`; None posts no reply (a holder that is silent)."""
    rows: list[dict] = []
    asked: list[dict] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def reply(self, doc) -> None:
            body = json.dumps(doc).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            sent = json.loads(self.rfile.read(int(self.headers["content-length"])))
            rows.append({"id": f"m{len(rows) + 1}", "content": sent["content"]})
            mine = rows[-1]["id"]
            req = json.loads(sent["content"])
            if sent["channel"] == "t:control" and req.get("kind") == "request":
                asked.append(req)
                data = answer(req)
                if data is not None:
                    rows.append({"id": f"m{len(rows) + 1}", "content": json.dumps(
                        {"v": 1, "kind": "reply", "id": "r", "in_reply_to": req["id"], "from": req["to"][0],
                         "op": req["op"], "ts": "t", "ok": True, "data": {req["op"]: data}})})
            self.reply({"id": mine})

        def do_GET(self):
            since = self.path.split("since_id=")[1].split("&")[0] if "since_id=" in self.path else None
            ids = [r["id"] for r in rows]
            after = rows[ids.index(since) + 1:] if since in ids else rows
            self.reply({"messages": after if "channel=t%3Acontrol" in self.path else []})

        def log_message(self, *a):
            pass
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.asked = asked  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        # No case reaches the login's own relay, token or registry: a
        # closed port, a scratch home and a scratch placement until a case
        # starts its fake relay.
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        dead = socket.socket()
        dead.bind(("127.0.0.1", 0))
        dead_url = f"http://127.0.0.1:{dead.getsockname()[1]}"
        dead.close()
        login = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
        host = socket.gethostname().split(".")[0]
        registry = os.path.join(tmp, "registry.json")
        with open(registry, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "hosts": {host: {"operator": "user"}},
                       "placement": {login: host, "waiter": host, "user": host}}, fh)
        env = {**os.environ, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state"), "AGENT_FABRIC_ROOT": ROOT,
               "HOME": home, "CLAUDE_BRIDGE_URL": dead_url, "CLAUDE_BRIDGE_AUTH_TOKEN": "tok",
               "AGENT_FABRIC_HOSTS_REGISTRY": registry, "FABRIC_STATE_CHANNEL": "t:state:control",
               "FABRIC_CONTROL_CHANNEL": "t:control"}
        repo_a, repo_b = os.path.join(tmp, "alpha"), os.path.join(tmp, "beta")
        for r in (repo_a, repo_b):
            os.makedirs(r)
            subprocess.run(["git", "init", "-q", r], check=True, env=git_env())

        def run(*argv: str, cwd: str = repo_a) -> subprocess.CompletedProcess:
            return subprocess.run([JOBS, *argv], cwd=cwd, env=env, capture_output=True, text=True)

        def jobs() -> list[dict]:
            return json.loads(run("list", "--all", "--json").stdout)

        p = run("list")
        check("an empty list says so", p.returncode == 0 and "no open jobs" in p.stdout, p.stdout + p.stderr)

        p = run("add", "first  job", "--topic", "memory drain")
        check("add queues j1 in the directory's working copy",
              p.returncode == 0 and "j1" in p.stdout and jobs()[0]["working_copy"] == repo_a
              and jobs()[0]["state"] == "queued" and jobs()[0]["title"] == "first job", p.stdout + p.stderr)
        run("add", "second", "--working-copy", repo_b)
        check("--working-copy names another repository", jobs()[1]["working_copy"] == repo_b, repr(jobs()))
        check("a job the agent adds has source self", jobs()[0]["source"] == {"kind": "self"}, repr(jobs()[0]))

        check("start makes a job active", run("start", "j1").returncode == 0 and jobs()[0]["state"] == "active")
        p = run("start", "j2")
        check("a second active job is refused", p.returncode == 1 and "j1 is active" in p.stderr
              and jobs()[1]["state"] == "queued", p.stderr)

        p = run("block", "j1", "a review of the PR")
        check("block records what it waits on", p.returncode == 0 and jobs()[0]["blocked_on"] == "a review of the PR",
              p.stdout + p.stderr)
        mid = "01a11a18-4728-7d8b-afd9-0edb2d30a59c"
        p = run("block", "j1", "--on-request", mid.upper())
        check("block --on-request keeps the message id as waits_on", p.returncode == 0
              and jobs()[0].get("waits_on") == mid and jobs()[0]["blocked_on"] == f"request {mid}", p.stderr + repr(jobs()[0]))
        p = run("block", "j1", "--on-request", "17")
        check("--on-request refuses what is not a MESSAGE-ID, and keeps the list", p.returncode == 1
              and "takes a MESSAGE-ID" in p.stderr and jobs()[0].get("waits_on") == mid, p.stderr)
        p = run("block", "j1", "a review again")
        check("blocked on something else: the request is no longer waited on", p.returncode == 0
              and "waits_on" not in jobs()[0], repr(jobs()[0]))
        p = run("block", "j1")
        check("block with nothing to wait on is refused", p.returncode == 1 and "waits on" in p.stderr, p.stderr)
        run("block", "j1", "--on-request", mid)
        run("start", "j1")
        check("leaving blocked drops waits_on", "waits_on" not in jobs()[0], repr(jobs()[0]))
        run("block", "j1", "a review of the PR")
        run("start", "j2")
        p = run("deliver", "j2", "org/repo#12", "abc1234")
        check("deliver names its artifacts", jobs()[1]["state"] == "delivered"
              and jobs()[1]["artifacts"] == ["org/repo#12", "abc1234"], p.stdout + p.stderr)
        run("deliver", "j2", "abc1234", "org/repo#13")
        check("a second deliver adds, never duplicates",
              jobs()[1]["artifacts"] == ["org/repo#12", "abc1234", "org/repo#13"], repr(jobs()[1]))
        run("done", "j2")
        p = run("start", "j2")
        check("a closed job is not reopened", p.returncode == 1 and "not reopened" in p.stderr, p.stderr)
        run("drop", "j1", "superseded by another job")
        check("drop keeps its reason", jobs()[0]["state"] == "dropped"
              and jobs()[0]["reason"] == "superseded by another job")

        p = run("add", "red\x1b[31m title")
        check("a control character in a title is refused", p.returncode == 1 and "control character" in p.stderr, p.stderr)
        p = run("add", "two\tlines\nof title")
        check("tab and newline collapse, as before", p.returncode == 0 and "two lines of title" in p.stdout, p.stdout + p.stderr)
        run("drop", p.stdout.split()[1] if p.returncode == 0 else "j0", "a test")
        p = run("list")
        check("list hides closed jobs", p.stdout.strip() == "no open jobs", p.stdout)
        p = run("list", "--all")
        check("list --all shows them", "j1" in p.stdout and "j2" in p.stdout, p.stdout)
        p = run("show", "j2")
        check("show gives the job in full", "artifacts:" in p.stdout and "org/repo#13" in p.stdout, p.stdout)
        p = run("show", "j2", "--line")
        check("show --line is one line for an opening prompt", p.stdout.count("\n") == 1
              and p.stdout.startswith("j2, second (") and "artifacts org/repo#12, abc1234, org/repo#13" in p.stdout, p.stdout)
        p = run("show", "j2", "--field", "working_copy")
        check("show --field gives one value", p.stdout.strip() == repo_b, p.stdout)
        p = run("show", "j9")
        check("an unknown id is refused by name", p.returncode == 1 and "no job j9" in p.stderr, p.stderr)
        check("the log keeps every state change",
              [e["state"] for e in jobs()[1]["log"]] == ["queued", "active", "delivered", "delivered", "done"],
              repr(jobs()[1]["log"]))

        # --project finds this login's checkout of the project beside the
        # working copy it runs in — never the current one for another project.
        gz = os.path.join(tmp, "gzapp-copy")
        subprocess.run(["git", "init", "-q", gz], check=True, env=git_env())
        subprocess.run(["git", "-C", gz, "remote", "add", "origin", "git@github.com:gzapi-org/gzapp.git"], check=True, env=git_env())
        env["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state-project")
        p = run("add", "a gzapp job", "--project", "gzapp")
        check("--project finds the project's checkout beside this one",
              p.returncode == 0 and jobs()[0]["working_copy"] == gz and jobs()[0]["project"] == "gzapp", p.stderr + repr(jobs()))
        p = run("add", "a job nowhere", "--project", "kutaisi-shop-transit")
        check("no checkout of it: no working copy, and said", p.returncode == 0 and jobs()[1]["working_copy"] is None
              and "no working copy of kutaisi-shop-transit" in p.stderr, p.stderr + repr(jobs()[1]))

        # A binding names a project; an unregistered checkout falls back to
        # it in resolve_context, and must still never pass for that project.
        env["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state-bound")
        os.makedirs(os.path.join(tmp, "state-bound", "agents", login))
        with open(os.path.join(tmp, "state-bound", "agents", login, "binding.json"), "w", encoding="utf-8") as fh:
            json.dump({"agent": login, "host": host, "role": "backend-dev", "project": "gzapp"}, fh)
        unreg = os.path.join(tmp, "aaa-unregistered")   # sorts before gzapp-copy
        subprocess.run(["git", "init", "-q", unreg], check=True, env=git_env())
        p = run("add", "a gzapp job", "--project", "gzapp", cwd=unreg)
        check("the bound project's job skips an unregistered checkout, the current one included",
              p.returncode == 0 and jobs()[0]["working_copy"] == gz, p.stderr + repr(jobs()))
        p = run("add", "a job here", cwd=unreg)
        check("a job in an unregistered checkout is not the bound project's", jobs()[1]["project"] is None
              and jobs()[1]["working_copy"] == unreg, repr(jobs()[1]))
        p = run("next", "j2", cwd=unreg)
        check("next in an unregistered checkout, for a job added there: continue here", p.returncode == 0
              and "continue here" in p.stdout and "fabric-fresh" not in p.stdout, p.stdout + p.stderr)
        run("drop", "j2", "a test")
        os.makedirs(os.path.join(repo_a, "sub"), exist_ok=True)
        p = run("add", "from a subdirectory", "--working-copy", os.path.join(repo_a, "sub"))
        check("--working-copy is stored as its checkout's toplevel", jobs()[2]["working_copy"] == repo_a, repr(jobs()[2]))

        # next: the restart rule, one branch per case.
        env["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state-next")
        p = run("next")
        check("next with nothing queued is refused", p.returncode == 1 and "no queued job" in p.stderr, p.stderr)
        run("add", "a", "--topic", "drain")
        run("add", "b", "--topic", "drain")
        run("add", "c", "--topic", "routing")
        run("add", "d", "--topic", "routing", "--working-copy", repo_b)
        run("add", "e")
        run("add", "f")
        p = run("next")
        check("the first job is compared with the directory: continue", p.returncode == 0
              and "j1" in p.stdout and "continue here" in p.stdout and "repository only" in p.stdout, p.stdout)
        p = run("next")
        check("next refuses while a job is active", p.returncode == 1 and "still active" in p.stderr, p.stderr)
        run("deliver", "j1", "x#1")
        p = run("next")
        check("same repository and topic: continue here", "j2" in p.stdout and "continue here" in p.stdout
              and "fabric-fresh" not in p.stdout and "repository only" not in p.stdout, p.stdout)
        run("done", "j2")
        p = run("next")
        check("another topic: a fresh session", "fresh session" in p.stdout and "topic 'routing'" in p.stdout
              and "fabric-fresh --job j3" in p.stdout, p.stdout)
        check("next makes the job it names active", jobs()[2]["state"] == "active", repr(jobs()[2]))
        run("block", "j3", "a reply")
        p = run("next")
        check("another working copy: a fresh session", "fresh session" in p.stdout and repo_b in p.stdout
              and "fabric-fresh --job j4" in p.stdout, p.stdout)
        run("done", "j4")
        p = run("next", "j3")
        check("a named blocked job can be next", p.returncode == 0 and "j3" in p.stdout
              and "fabric-fresh --job j3" in p.stdout, p.stdout)
        run("done", "j3")
        p = run("next", "--json")
        verdict = json.loads(p.stdout or "{}")
        check("no topic on the next job: repository only, said", verdict.get("job") == "j5"
              and verdict.get("fresh") is False and "no topic on j5" in (verdict.get("caveat") or ""), p.stdout)
        run("done", "j5")
        p = run("next", "j3")
        check("next refuses a closed job", p.returncode == 1 and "next takes a queued" in p.stderr, p.stderr)

        # Priority (ADR-037 rule 7): the highest first, then the oldest; an
        # active job is never passed; a blocked one keeps its place.
        env["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state-priority")
        run("add", "old normal")
        run("add", "low one", "--priority", "low")
        run("add", "high one", "--priority", "high")
        run("add", "second high", "--priority", "high")
        run("add", "blocked blocker", "--priority", "blocking")
        check("add --priority stores it; none given is normal",
              [j.get("priority") for j in jobs()] == ["normal", "low", "high", "high", "blocking"], repr(jobs()))
        run("start", "j5")
        run("block", "j5", "a reply")
        p = run("list")
        check("list shows each job's priority", " high " in p.stdout and " low " in p.stdout, p.stdout)
        p = run("next")
        check("next takes the highest priority, not the oldest", p.returncode == 0 and p.stdout.startswith("j3 "),
              p.stdout + p.stderr)
        p = run("next")
        check("the active job is never preempted, a blocking one notwithstanding", p.returncode == 1
              and "j3 is still active" in p.stderr, p.stderr)
        run("done", "j3")
        p = run("next")
        check("equal priority: the oldest first", p.stdout.startswith("j4 "), p.stdout + p.stderr)
        run("done", "j4")
        check("a blocked job keeps its place: it is not taken by next",
              run("next").stdout.startswith("j1 ") and jobs()[4]["state"] == "blocked", repr(jobs()[4]))
        run("done", "j1")
        p = run("prio", "j2", "blocking")
        check("prio sets a queued job's priority", p.returncode == 0 and jobs()[1]["priority"] == "blocking", p.stderr)
        p = run("prio", "j1", "high")
        check("prio refuses a closed job", p.returncode == 1 and "closed job" in p.stderr, p.stderr)
        p = run("prio", "j2", "urgent")
        check("prio takes only the four priorities", p.returncode == 2 and "invalid choice" in p.stderr, p.stderr)
        p = run("add", "x", "--priority", "urgent")
        check("add --priority takes only the four", p.returncode == 2 and len(jobs()) == 5, p.stderr)

        # A list written before priorities reads normal; a value outside the
        # four is unknown, never normal.
        lst = os.path.join(tmp, "state-priority", "agents", os.listdir(os.path.join(tmp, "state-priority", "agents"))[0], "jobs.json")
        with open(lst, encoding="utf-8") as fh:
            doc = json.load(fh)
        for j in doc["jobs"]:
            j.pop("priority", None)
        doc["jobs"][1]["state"] = "queued"
        doc["jobs"].append({**doc["jobs"][1], "id": "j6", "title": "later", "priority": "high"})
        with open(lst, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        p = run("next")
        check("an old list reads normal: a high job added after it goes first", p.stdout.startswith("j6 "), p.stdout + p.stderr)
        run("done", "j6")
        doc = json.loads(open(lst, encoding="utf-8").read())
        doc["jobs"][1]["priority"] = "urgent"
        with open(lst, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        p = run("next")
        check("an unknown stored priority refuses to order the queue, by name", p.returncode == 1
              and "j2 has priority 'urgent'" in p.stderr and doc["jobs"][1]["state"] == "queued", p.stderr)
        p = run("list")
        check("list shows an unknown priority as '?'", p.returncode == 0 and "j2    queued    ? " in p.stdout, p.stdout)

        # add --request: the message read through the inbox's own replay,
        # against a fake relay; only what is addressed to this login.
        env["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state-request")
        me = f"TO: {socket.gethostname().split('.')[0]}/{subprocess.run(['id', '-un'], capture_output=True, text=True).stdout.strip()}"
        relay = fake_relay([
            {"seq": 11, "id": "r11", "ts": "T", "sender": "other-host/sender", "content": message("REQUEST", me, "a", "build the thing")},
            {"seq": 12, "id": "r12", "ts": "T", "sender": "other-host/sender", "content": message("REQUEST", "TO: h/someone-else", "b", "not mine")},
            {"seq": 13, "id": "r13", "ts": "T", "sender": "other-host/sender", "content": message("INFO", me, "c", "just news")},
            {"seq": 14, "id": "r14", "ts": "T", "sender": "other-host/sender", "content": message("REQUEST", me, "d", "elsewhere", "another")},
        ])
        env.update({"CLAUDE_BRIDGE_URL": f"http://127.0.0.1:{relay.server_address[1]}",
                    "GZCOORD_CHANNEL": "fixture:chan"})
        try:
            p = run("add", "--request", "01a09fc1-0000-7000-8000-00000000000a", "--topic", "thing")
            check("a request outside its project's working copy asks for one", p.returncode == 1
                  and "for project fixture" in p.stderr and not jobs(), p.stderr)
            p = run("add", "--request", "01a09fc1-0000-7000-8000-00000000000a", "--topic", "thing",
                    "--working-copy", repo_a)
            got = jobs()
            check("--request fills the job from the message", p.returncode == 0 and len(got) == 1
                  and got[0]["working_copy"] == repo_a
                  and got[0]["title"] == "build the thing" and got[0]["project"] == "fixture"
                  and got[0]["source"] == {"kind": "request", "message_id": "01a09fc1-0000-7000-8000-00000000000a",
                                           "from": "other-host/sender", "seq": 11}, p.stdout + p.stderr + repr(got))
            p = run("add", "--request", "11")
            check("the same message twice is refused by name", p.returncode == 1 and "already j1" in p.stderr, p.stderr)
            p = run("add", "--request", "12")
            check("a message not addressed to this login is refused", p.returncode == 1
                  and "not addressed to this login" in p.stderr and len(jobs()) == 1, p.stderr)
            p = run("add", "--request", "14")
            check("a request for another project asks for its working copy", p.returncode == 1
                  and "for project another" in p.stderr, p.stderr)
            p = run("add", "--request", "14", "--working-copy", repo_b)
            check("--working-copy settles it", p.returncode == 0 and jobs()[-1]["project"] == "another", p.stderr)
            p = run("add", "--request", "13", "--auto", "--working-copy", repo_a)
            check("the automatic intake skips what is not a REQUEST", p.returncode == 0 and len(jobs()) == 2, p.stderr)
            p = run("add", "--request", "11", "--auto")
            check("the automatic intake skips a listed request quietly", p.returncode == 0
                  and not p.stderr and len(jobs()) == 2, p.stderr)
            # inbox exits 2 for a control channel too; only its own
            # {"addressed": false} answer means "not for this login".
            p = subprocess.run([JOBS, "add", "--request", "11", "--working-copy", repo_a], cwd=repo_a,
                               env={**env, "GZCOORD_CHANNEL": "fixture:control"}, capture_output=True, text=True)
            check("an inbox refusal is said as itself, not as 'not addressed'", p.returncode == 1
                  and "cannot read message 11" in p.stderr and "not addressed" not in p.stderr, p.stderr)
        finally:
            relay.shutdown()
            relay.server_close()

        # Blocking, derived (ADR-037 rule 8): a queued job whose request an
        # account waits on ranks blocking, its stored priority kept.
        env["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state-waits")
        env["CLAUDE_BRIDGE_URL"] = dead_url
        waited, other = "01a11a18-4728-7d8b-afd9-0edb2d30a59c", "01a11a19-0bea-70c7-b667-1e1e5a74dbe1"
        run("add", "high and not waited", "--priority", "high")
        run("add", "low but waited", "--priority", "low")
        run("add", "plain")
        lst = os.path.join(tmp, "state-waits", "agents", login, "jobs.json")
        doc = json.loads(open(lst, encoding="utf-8").read())
        doc["jobs"][1]["source"] = {"kind": "request", "message_id": waited, "from": f"{host}/waiter", "seq": 1}
        doc["jobs"][2]["source"] = {"kind": "request", "message_id": other, "from": f"{host}/waiter", "seq": 2}
        with open(lst, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        p = run("list")
        check("stream down: list says so and shows stored priorities", p.returncode == 0
              and "state stream could not be read" in p.stderr and "stored priorities decide" in p.stderr
              and "ranks blocking" not in p.stdout, p.stdout + p.stderr)

        # queue.mjs reads the record's age against the real clock: a minute
        # old is fresh, two hours old is past its 20-minute bound.
        def ago(minutes: int) -> str:
            return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

        def state_rec(frm: str, waits_on, ts: str | None = None, i: int = 0) -> dict:
            ts = ts or ago(1)
            rec = {"v": 1, "kind": "state", "from": frm, "ts": ts, "sessions": []}
            if waits_on is not None:
                rec["waits_on"] = waits_on
            return {"id": f"s{i}", "seq": i, "ts": ts, "sender": frm, "content": json.dumps(rec)}
        state_rows = [
            state_rec(f"{host}/waiter", [other], i=1),             # older: superseded below
            state_rec(f"{host}/waiter", [waited], i=2),
            state_rec("elsewhere/unplaced", [other], i=3),         # no placed address: skipped
            state_rec(f"{host}/user", ["not-an-id"], i=4),         # not agentd's shape: skipped
        ]
        relay = fake_relay([], state_rows)
        env["CLAUDE_BRIDGE_URL"] = f"http://127.0.0.1:{relay.server_address[1]}"
        try:
            p = run("list")
            row = next((x for x in p.stdout.splitlines() if x.startswith("j2 ")), "")
            check("a waited request ranks blocking, its stored priority shown, and the waiter named",
                  p.returncode == 0 and " low " in row and f"ranks blocking: {host}/waiter waits on it" in row
                  and not p.stderr, p.stdout + p.stderr)
            check("only the newest record of an account counts; an unplaced or malformed one is skipped",
                  "ranks blocking" not in next((x for x in p.stdout.splitlines() if x.startswith("j3 ")), "x"), p.stdout)
            got = json.loads(run("list", "--json").stdout)
            check("list --json gives both priorities and the waiters", [(j["priority"], j["effective_priority"], j["waited_by"]) for j in got]
                  == [("high", "high", []), ("low", "blocking", [f"{host}/waiter"]), ("normal", "normal", [])], repr(got))
            p = subprocess.run([JOBS, "list"], cwd=repo_a, capture_output=True, text=True,
                               env={**env, "AGENT_FABRIC_HOSTS_REGISTRY": os.path.join(tmp, "no-registry.json")})
            check("an unreadable hosts registry is said, never read as nobody waiting", p.returncode == 0
                  and "the hosts registry cannot be read" in p.stderr and "ranks blocking" not in p.stdout, p.stderr)
            got = json.loads(run("list", "--json", "--stored").stdout)
            check("--stored reads no stream", got[1]["effective_priority"] == "low", repr(got[1]))
            p = run("next")
            check("next takes the effectively blocking job before a high one, and says why", p.returncode == 0
                  and p.stdout.startswith("j2 ") and f"ranked blocking: {host}/waiter waits on its request (stored low)" in p.stdout,
                  p.stdout + p.stderr)
            check("its stored priority stays", jobs()[1]["priority"] == "low", repr(jobs()[1]))
            # A waiter whose record is past the bound still ranks the job
            # blocking (rule 8), named with the record's age and said stale.
            state_rows.append(state_rec(f"{host}/user", [other], ts=ago(120), i=5))
            p = run("list")
            row = next((x for x in p.stdout.splitlines() if x.startswith("j3 ")), "")
            check("a stale waiter still ranks the job blocking, named with its record's age",
                  p.returncode == 0 and re.search(rf"ranks blocking: {re.escape(host)}/user \(state record 12[01] min old: stale\) waits on it$", row)
                  is not None and not p.stderr, p.stdout + p.stderr)
            got = json.loads(run("list", "--json").stdout)
            j3 = next(j for j in got if j["id"] == "j3")
            check("list --json carries the stale waiter's age in seconds", j3["effective_priority"] == "blocking"
                  and set(j3["stale_waiters"]) == {f"{host}/user"} and 7200 <= j3["stale_waiters"][f"{host}/user"] < 7300
                  and next(j for j in got if j["id"] == "j2")["stale_waiters"] == {}, repr(j3))
            run("done", "j2")
            p = run("next")
            check("next names a stale waiter the same way", p.returncode == 0 and p.stdout.startswith("j3 ")
                  and re.search(rf"ranked blocking: {re.escape(host)}/user \(state record 12[01] min old: stale\) waits on its request",
                                p.stdout) is not None, p.stdout + p.stderr)
            run("done", "j3")
            # A queued job from a message again, so the stream is read below.
            run("add", "from a message again")
            doc = json.loads(open(lst, encoding="utf-8").read())
            doc["jobs"][-1]["source"] = {"kind": "request", "message_id": other, "from": f"{host}/waiter", "seq": 3}
            with open(lst, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
        finally:
            relay.shutdown()
            relay.server_close()
        env["CLAUDE_BRIDGE_URL"] = dead_url
        p = run("next")
        check("stream down: next says so and takes the stored order", p.returncode == 0 and p.stdout.startswith("j1 ")
              and "stored priorities decide" in p.stderr, p.stdout + p.stderr)
        env["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state-nowait")
        run("add", "a plain job")
        p = run("list")
        check("no queued job from a message: the stream is not read, nothing said", p.returncode == 0 and not p.stderr,
              p.stderr)

        # The role's pool (ADR-037 rule 9), through queue.mjs against a fake
        # holder: list, claim onto this list, next's offer.
        env["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state-pool")
        os.makedirs(os.path.join(tmp, "state-pool", "agents", login))
        with open(os.path.join(tmp, "state-pool", "agents", login, "binding.json"), "w", encoding="utf-8") as fh:
            json.dump({"agent": login, "host": host, "role": "python-dev"}, fh)
        env["FABRIC_QUEUE_WAIT_MS"] = "1500"
        pool_jobs = [{"id": "p2", "role": "python-dev", "title": "port the launcher", "topic": "launcher",
                      "project": None, "priority": "high", "created": "t"},
                     {"id": "p1", "role": "python-dev", "title": "older normal", "topic": None, "project": None,
                      "priority": "normal", "created": "t"}]

        claims: set[str] = set()   # what this holder has recorded: a repeat claim comes back with again

        def holder(req: dict):
            if req["op"] == "pool-list":
                return {"status": "ok", "role": req["args"]["role"],
                        "jobs": pool_jobs if req["args"]["role"] == "python-dev" else []}
            if req["args"]["id"] == "p9":
                return {"status": "refused", "reason": "p9 is claimed by h/other (t)"}
            if req["args"]["id"] == "p8":
                return None
            if req["args"]["id"] == "p7":
                return {"status": "claimed", "job": {**pool_jobs[0], "id": "p7", "title": "bad\x1b[2J title"}}
            if req["args"]["id"] == "p6":
                return {"status": "claimed", "job": {"title": "no id"}}
            if req["args"]["id"] == "p5":
                return {"status": "claimed", "job": {**pool_jobs[0], "id": "p5", "priority": "urgent"}}
            if req["args"]["id"] == "p4":
                return {"status": "claimed", "job": {**pool_jobs[0], "id": "p3"}}
            if req["args"]["id"] == "p3":
                return {"status": "claimed", "job": {**pool_jobs[0], "id": "p3", "title": "landed fresh"}}
            again = req["args"]["id"] in claims
            claims.add(req["args"]["id"])
            return {"status": "claimed", "job": next(j for j in pool_jobs if j["id"] == req["args"]["id"]),
                    **({"again": True} if again else {})}
        relay = fake_holder(holder)
        env["CLAUDE_BRIDGE_URL"] = f"http://127.0.0.1:{relay.server_address[1]}"
        try:
            p = run("next")
            check("nothing queued: next offers the bound role's first pool job, and claims nothing", p.returncode == 1
                  and "the python-dev pool offers p2" in p.stderr and "fabric-jobs pool-claim p2" in p.stderr
                  and not jobs(), p.stderr)
            check("the list asked for the bound role, of the one host's operator",
                  relay.asked[-1]["args"] == {"role": "python-dev"} and relay.asked[-1]["to"] == [f"{host}/user"]
                  and relay.asked[-1]["from"] == f"{host}/{login}", repr(relay.asked[-1]))
            p = run("pool-list")
            check("pool-list prints the pool in the holder's order", p.returncode == 0
                  and p.stdout.splitlines()[0].startswith("p2    high     python-dev [launcher]: port the launcher"),
                  p.stdout + p.stderr)
            p = run("pool-list", "--role", "web-dev")
            check("an empty pool is said", p.returncode == 0 and p.stdout.strip() == "the web-dev pool is empty", p.stdout)
            p = run("pool-claim", "p2")
            got = jobs()
            check("a claim lands the job on this list, queued, source pool, its priority kept", p.returncode == 0
                  and p.stdout.startswith("claimed j1 ") and got[0]["state"] == "queued" and got[0]["priority"] == "high"
                  and got[0]["topic"] == "launcher"
                  and got[0]["source"] == {"kind": "pool", "pool_id": "p2", "from": f"{host}/user"}, p.stdout + p.stderr + repr(got))
            check("the claim request names only the id, never a role", relay.asked[-1]["args"] == {"id": "p2"},
                  repr(relay.asked[-1]))
            p = run("pool-claim", "p2")
            check("claimed again: already listed, not a second job", p.returncode == 0 and "already listed j1" in p.stdout
                  and len(jobs()) == 1, p.stdout + p.stderr)
            claims.clear()   # the holder's pool file recreated: p2 is a new job under an old id
            p = run("pool-claim", "p2")
            check("a first claim is a new job, even where an open job holds the same holder's id", p.returncode == 0
                  and p.stdout.startswith("claimed j2 ") and len(jobs()) == 2, p.stdout + p.stderr)
            run("drop", "j2", "a test")
            p = run("pool-claim", "p9")
            check("a refused claim is said with the holder's reason", p.returncode == 1
                  and "refused: p9 is claimed by h/other" in p.stderr and len(jobs()) == 2, p.stderr)
            p = run("pool-claim", "p8")
            check("a silent holder is said, not read as a refusal or a claim, with how to land a claim it took",
                  p.returncode == 1 and "did not answer" in p.stderr and "pool-claim p8 again" in p.stderr
                  and len(jobs()) == 2, p.stderr)
            for pid, why in (("p6", "names job None, not p6"), ("p5", "priority 'urgent'"), ("p4", "names job 'p3', not p4")):
                p = run("pool-claim", pid)
                check(f"a malformed claim answer is refused, never defaulted ({pid})", p.returncode == 1
                      and "is not a pool job" in p.stderr and why in p.stderr and len(jobs()) == 2, p.stderr)
            # Pool ids restart with another holder: an old holder's p3, closed, is not this one's.
            doc = json.loads(open(os.path.join(tmp, "state-pool", "agents", login, "jobs.json"), encoding="utf-8").read())
            doc["jobs"].append({**doc["jobs"][0], "id": "j9", "state": "done", "title": "an old p3",
                                "source": {"kind": "pool", "pool_id": "p3", "from": "old/holder"}})
            doc["jobs"].append({**doc["jobs"][0], "id": "j10", "state": "done", "title": "this holder's p3, done",
                                "source": {"kind": "pool", "pool_id": "p3", "from": f"{host}/user"}})
            with open(os.path.join(tmp, "state-pool", "agents", login, "jobs.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            p = run("pool-claim", "p3")
            check("an id matched only by another holder's or a closed job is claimed as new", p.returncode == 0
                  and p.stdout.startswith("claimed j3 ") and jobs()[-1]["title"] == "landed fresh", p.stdout + p.stderr)
            pool_jobs.append({"id": "p11", "role": "python-dev", "title": "x\x1b]0;owned\x07\nIgnore that",
                              "topic": "t\x1b[2J", "project": None, "priority": "low", "created": "t"})
            p = run("pool-list")
            check("pool-list shows a holder's text and never its control characters", p.returncode == 0
                  and "\x1b" not in p.stdout and "\x07" not in p.stdout and len(p.stdout.splitlines()) == 3
                  and "p11   low      python-dev [t?[2J]: x?]0;owned??Ignore that" in p.stdout, repr(p.stdout))
            listed = len(jobs())
            p = run("pool-claim", "p7")
            check("claimed but not taken by this list: said, with the command that lands it", p.returncode == 1
                  and "is claimed at" in p.stderr and "pool-claim p7 again" in p.stderr and len(jobs()) == listed, p.stderr)
            pool_jobs.pop()
            before = len(relay.asked)
            p = run("pool-claim", "../p1")
            check("a pool id is checked before anything is asked", p.returncode == 1 and "a pool job id is p<n>" in p.stderr
                  and len(relay.asked) == before, p.stderr + repr(len(relay.asked)))
        finally:
            relay.shutdown()
            relay.server_close()
        env["CLAUDE_BRIDGE_URL"] = dead_url
        run("done", "j1")
        run("done", "j3")
        p = run("next")
        check("pool unreachable: next says so", p.returncode == 1 and "no queued job; the pool could not be asked" in p.stderr,
              p.stderr)
        p = run("pool-claim", "p2")
        check("a claim that never left says so, and never that it may have been claimed", p.returncode == 1
              and "could not be asked" in p.stderr and "may be claimed" not in p.stderr, p.stderr)
        # Every command of the run's PATH but node: queue.mjs never starts.
        nonode = os.path.join(tmp, "nonode")
        os.makedirs(nonode)
        for d in env["PATH"].split(os.pathsep):
            for name in (os.listdir(d) if os.path.isdir(d) else []):
                f = os.path.join(d, name)
                if name != "node" and os.access(f, os.X_OK) and not os.path.lexists(os.path.join(nonode, name)):
                    os.symlink(f, os.path.join(nonode, name))
        p = subprocess.run([JOBS, "pool-claim", "p2"], cwd=repo_a, capture_output=True, text=True,
                           env={**env, "PATH": nonode})
        check("node unable to start: a claim that never left, never 'may be claimed'", p.returncode == 1
              and "node could not run" in p.stderr and "may be claimed" not in p.stderr, p.stderr)

        class Fails(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(500)
                self.send_header("content-length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass
        failing = http.server.HTTPServer(("127.0.0.1", 0), Fails)
        threading.Thread(target=failing.serve_forever, daemon=True).start()
        try:
            p = subprocess.run([JOBS, "pool-claim", "p2"], cwd=repo_a, capture_output=True, text=True,
                               env={**env, "CLAUDE_BRIDGE_URL": f"http://127.0.0.1:{failing.server_address[1]}"})
            check("a post that failed after it may have been written is unknown: said with how to land it",
                  p.returncode == 1 and "HTTP 500" in p.stderr and "pool-claim p2 again" in p.stderr, p.stderr)
        finally:
            failing.shutdown()
            failing.server_close()

        state = os.path.join(tmp, "state", "agents")
        login = os.listdir(state)[0]
        with open(os.path.join(state, login, "jobs.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        check("the file names its agent and host", doc["agent"] == login and doc.get("host"), repr(doc)[:200])
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
