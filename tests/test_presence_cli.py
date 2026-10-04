#!/usr/bin/env python3
"""runtime/control/presence.mjs check — the CLI the Python sender asks
presence through (agent-fabric ADR-040 §7, Wave 7; the coordinator's
decision of 2026-10-04: the control channel's shapes stay in the control
plane). Its contract is in that file's header; this holds it from the
caller's side, through the real process: the request on stdin, the answer
as JSON on stdout, the status as its summary (0 clean, 4 a definite
problem, 5 silent, 6 unavailable, 2 usage), and a malformed request
refused without the parser's message, which would quote the token.
A relay stub answers presence on the control channel from a table.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESENCE = os.path.join(HERE, "runtime", "control", "presence.mjs")
TOKEN = "tok-presence-fixture-SECRET"


def stub(answers: dict, status: int = 200) -> tuple[http.server.ThreadingHTTPServer, list]:
    """A relay: POST /api/send on the control channel records the request;
    GET /api/messages there returns a reply per expected address that has
    an answer in the table — none for a silent one."""
    asked: list = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def reply(self, code: int, doc: object) -> None:
            data = json.dumps(doc).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):  # noqa: N802 — the stdlib's name
            body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
            if status != 200:
                return self.reply(status, {})
            if body.get("channel") == "fabric:control":
                asked.append(json.loads(body["content"]))
            self.reply(200, {"id": "ctl", "seq": 1})

        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            messages = []
            if q.get("channel") == ["fabric:control"]:
                for r in asked:
                    targets = list(answers) if r["to"] == "*" else r["to"]
                    for i, a in enumerate(t for t in targets if answers.get(t)):
                        messages.append({"id": f"{r['id']}-{i}", "content": json.dumps(
                            {"kind": "reply", "in_reply_to": r["id"], "from": a, "data": {"presence": answers[a]}})})
            self.reply(200, {"messages": messages})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, asked


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good:
            print(f"      {detail}")
        fails += not good

    tmp = tempfile.mkdtemp(prefix="presence-cli-")
    try:
        registry = os.path.join(tmp, "hosts.json")
        with open(registry, "w") as fh:
            json.dump({"version": 1, "hosts": {"h": {"operator": "user"}}, "placement": {"alpha": "h", "beta": "h"}}, fh)
        base = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE_"))}
        base.update(AGENT_FABRIC_HOSTS_REGISTRY=registry, GZCOORD_PRESENCE_WAIT_MS="800")

        def ask(metadata: dict, url: str = "http://127.0.0.1:1", args: tuple = ("check",), raw: str | None = None):
            req = raw if raw is not None else json.dumps({"metadata": metadata, "from": "h/me", "token": TOKEN})
            r = subprocess.run(["node", PRESENCE, *args], input=req, capture_output=True, text=True, timeout=60,
                               env={**base, "CLAUDE_BRIDGE_URL": url})
            try:
                answer = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else None
            except ValueError:
                answer = None
            return r.returncode, answer, r.stderr

        up = {"status": "ok", "online": True, "role": "web-dev"}
        down = {"status": "ok", "online": False, "role": "web-dev"}
        failed = {"status": "failed", "error": "pgrep: spawn pgrep ENOENT"}

        print("usage")
        rc, _a, err = ask({}, args=())
        check("no subcommand: exit 2, a usage line", rc == 2 and "usage: presence.mjs check" in err, (rc, err))
        rc, _a, err = ask({}, raw='{"token": "' + TOKEN + '", not json')
        check("stdin that is not JSON: exit 2, and the token is never echoed", rc == 2 and TOKEN not in err
              and "stdin is not one JSON object" in err, (rc, err))
        rc, _a, err = ask({}, raw=json.dumps({"metadata": {}, "from": "h/me"}))
        check("a request with no token: exit 2, named", rc == 2 and '"token"' in err, (rc, err))

        print("answers")
        rc, a, _e = ask({"BROADCAST": "true"})
        check("a broadcast is not checked: exit 0", rc == 0 and a == {"checked": False}, (rc, a))
        rc, a, _e = ask({"TO": "h/nobody"})
        check("an address no host places: exit 4, not-placed", rc == 4 and a["problems"][0]["kind"] == "not-placed", (rc, a))
        for table, want_rc, want, label in (
                ({"h/alpha": up}, 0, [], "a running addressee: exit 0, no problem"),
                ({"h/alpha": down}, 4, ["offline"], "no session: exit 4, offline"),
                ({}, 5, ["silent"], "a control agent that does not answer: exit 5, silent — never offline"),
                ({"h/alpha": failed}, 6, ["unavailable"], "a presence that could not read its table: exit 6")):
            server, asked = stub(table)
            try:
                rc, a, err = ask({"TO": "h/alpha"}, url=f"http://127.0.0.1:{server.server_address[1]}")
            finally:
                server.shutdown()
                server.server_close()
            kinds = [p["kind"] for p in (a or {}).get("problems", [])]
            check(label, rc == want_rc and kinds == want and len(asked) == 1 and asked[0]["op"] == "presence",
                  (rc, a, err[-300:]))
        server, _asked = stub({"h/alpha": up})
        try:
            rc, a, _e = ask({"TO-ROLE": "web-dev"}, url=f"http://127.0.0.1:{server.server_address[1]}")
        finally:
            server.shutdown()
            server.server_close()
        check("a role with a running holder: exit 0", rc == 0 and a.get("problems") == [], (rc, a))
        server, _asked = stub({}, status=401)
        try:
            rc, a, err = ask({"TO": "h/alpha"}, url=f"http://127.0.0.1:{server.server_address[1]}")
        finally:
            server.shutdown()
            server.server_close()
        check("a refused token: exit 6, the status carried for the sender to read as the post's",
              rc == 6 and a.get("status") == 401 and TOKEN not in json.dumps(a) + err, (rc, a))
        rc, a, _e = ask({"TO": "h/alpha"}, url="http://127.0.0.1:1")
        check("a relay that cannot be reached: exit 6, an error with no status", rc == 6 and a.get("status") is None
              and a.get("error"), (rc, a))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"test_presence_cli: {'OK' if not fails else f'FAILED — {fails}'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
