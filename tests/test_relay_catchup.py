#!/usr/bin/env python3
"""tools/fabric/relay_catchup.py against a fake relay in this process: a new
account's cursor is put at the channel's newest message, as itself, with
its own token, which is never printed."""
from __future__ import annotations

import json
import os
import pwd
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from instance_fixtures import write_gzcoord_integrations

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "tools", "fabric", "relay_catchup.py")
TOKEN = "fixture-relay-token-not-a-secret"
ME = f"{socket.gethostname().split('.')[0]}/{pwd.getpwuid(os.getuid()).pw_name}"


class Relay(BaseHTTPRequestHandler):
    messages: list[dict] = []
    calls: list[tuple] = []
    fail = False

    def log_message(self, *a) -> None:
        pass

    def _send(self, code: int, obj: object) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        u = urlparse(self.path)
        Relay.calls.append(("GET", u.path, parse_qs(u.query), self.headers.get("Authorization")))
        if Relay.fail:
            return self._send(500, {"error": "down"})
        self._send(200, {"messages": Relay.messages})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Relay.calls.append(("POST", self.path, body, self.headers.get("Authorization")))
        self._send(200, {"ok": True})


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    server = HTTPServer(("127.0.0.1", 0), Relay)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    with tempfile.TemporaryDirectory() as home:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "GZCOORD_", "CLAUDE_BRIDGE_"))}
        # The integrations the cases name are the fixture operator's, never the checkout's.
        operator = write_gzcoord_integrations(os.path.join(home, "operator"),
                                              {"agent-fabric": (url, "gzapp:gzcoord"), "interweave": (url, "gzapp:gzcoord")})
        env.update(HOME=home, CLAUDE_BRIDGE_URL=url, AGENT_FABRIC_OPERATOR=operator)

        def run(*projects: str) -> subprocess.CompletedProcess:
            Relay.calls.clear()
            return subprocess.run([sys.executable, TOOL, *projects], env=env, capture_output=True, text=True, timeout=60)

        r = run("agent-fabric")
        check("no token: exit 1, said, nothing asked of the relay", r.returncode == 1 and "fabric-secrets sync first" in r.stderr
              and not Relay.calls, (r.returncode, r.stderr))
        os.makedirs(os.path.join(home, ".config", "agent-fabric"))
        with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), "w") as f:
            f.write(f"# marker\nexport OTHER=x\nexport CLAUDE_BRIDGE_AUTH_TOKEN='{TOKEN}'\n")

        Relay.messages = [{"id": "m-7", "seq": 7}, {"id": "m-12", "seq": 12}, {"id": "m-9", "seq": 9}]
        r = run("agent-fabric")
        acks = [c for c in Relay.calls if c[0] == "POST"]
        check("the newest message is acknowledged, as this account, on the project's channel",
              r.returncode == 0 and len(acks) == 1 and acks[0][1] == "/api/ack"
              and acks[0][2] == {"consumer_id": ME, "channel": "gzapp:gzcoord", "message_id": "m-12"}, (r.stdout, r.stderr, Relay.calls))
        check("…with its own token as the bearer", all(c[3] == f"Bearer {TOKEN}" for c in Relay.calls), Relay.calls)
        check("…and the token is printed nowhere", TOKEN not in r.stdout + r.stderr and "seq 12" in r.stdout, r.stdout)

        r = run("agent-fabric", "interweave")
        check("two projects on one channel: caught up once", len([c for c in Relay.calls if c[0] == "POST"]) == 1, Relay.calls)

        env["GZCOORD_CHANNEL"] = "elsewhere"
        r = run("agent-fabric")
        check("GZCOORD_CHANNEL overrides the integration, as the inbox does",
              [c[2]["channel"] for c in Relay.calls if c[0] == "POST"] == ["elsewhere"], Relay.calls)
        del env["GZCOORD_CHANNEL"]

        env["GZCOORD_CHANNEL"] = "fabric:control"
        r = run("agent-fabric")
        check("the control channel is refused, said, and nothing acknowledged there (positive control: the case above acknowledged)",
              r.returncode == 1 and "control channel" in r.stderr and not [c for c in Relay.calls if c[0] == "POST"],
              (r.returncode, r.stderr, Relay.calls))
        del env["GZCOORD_CHANNEL"]

        r = run("no-such-project")
        check("a project with no integration is said, and is not a failure",
              r.returncode == 0 and "no GZCoord integration" in r.stdout and not Relay.calls, (r.returncode, r.stdout))

        Relay.messages = []
        r = run("agent-fabric")
        check("an empty channel: nothing acknowledged", r.returncode == 0 and "no message yet" in r.stdout
              and not [c for c in Relay.calls if c[0] == "POST"], (r.stdout, Relay.calls))

        Relay.messages = ["not an object"]
        r = run("agent-fabric")
        check("a malformed answer from the relay: exit 1, said, no traceback (re-review of #77)",
              r.returncode == 1 and "relay-catchup:" in r.stderr and "Traceback" not in r.stderr, r.stderr)

        Relay.fail = True
        r = run("agent-fabric")
        check("a relay that refuses: exit 1, the status said, the token not", r.returncode == 1 and "500" in r.stderr
              and TOKEN not in r.stderr, (r.returncode, r.stderr))
    server.shutdown()
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
