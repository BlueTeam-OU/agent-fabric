#!/usr/bin/env python3
"""Tests for tools/fabric/control/gzcoord.py, the port of runtime/control/gzcoord.mjs.

gzcoord.test.mjs's cases of the control plane's own code (shellWord,
api, apiTimeoutMs, relayFailure) are ported case for case. Its cases of
whoami, identity, inboxRoot, integrationConfig, holdStatus, syncedVar
and token test the copy of the GZCoord tools gzcoord.mjs carried; here
those names ARE the GZCoord tools' (Wave 7), whose own suites hold them
(tests/test_gzcoord_port.py, test_gzcoord_protocol.py), so this holds
the binding: each name is that function, not another copy.
"""
from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import gzcoord as cg  # noqa: E402
from gzcoord import gzmsg, paths  # noqa: E402
from gzcoord.inbox_parts import config, hold, tokens  # noqa: E402

GZCOORD_MJS = os.path.join(HERE, "runtime", "control", "gzcoord.mjs")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    print("the GZCoord tools' functions, under gzcoord.mjs's names")
    for name, fn in (("whoami", gzmsg.whoami), ("load_taxonomy", gzmsg.load_taxonomy), ("find_taxonomy", gzmsg.find_taxonomy),
                     ("integration_config", config.integration_config), ("inbox_root", config.inbox_root),
                     ("token", tokens.token), ("synced_var", tokens.synced_var), ("synced_token", tokens.synced_token),
                     ("identity", tokens.identity), ("hold_status", hold.hold_status)):
        check(f"{name} is the GZCoord tools' own", getattr(cg, name, None) is fn)
    check("FABRIC_ROOT is the checkout the GZCoord tools name", cg.FABRIC_ROOT == paths.fabric_root())

    print("gzcoord.test.mjs: shellWord")
    check("'a'\"'\"'b' tail", cg.shell_word("'a'\"'\"'b' tail") == "a'b")
    check('inside "…" a backslash escapes only " and \\', cg.shell_word('"a\\"b\\\\c\\d"') == 'a"b\\c\\d')
    check("a\\ b c", cg.shell_word("a\\ b c") == "a b")
    check("  x  ", cg.shell_word("  x  ") == "x")
    check("an empty line is no value", cg.shell_word("") is None)
    check("'' is the empty word", cg.shell_word("''") == "")
    for bad in ("'open", '"open', "end\\", '"end\\'):
        check(f"unterminated {bad!r} is no value", cg.shell_word(bad) is None)
    check("a bad quote after the first word is not that word's", cg.shell_word("a 'b") == "a")
    check("a word holds - / = : and the like, as a token value does", cg.shell_word("ab-c/d=e:f+g.h tail") == "ab-c/d=e:f+g.h")
    import random
    rnd = random.Random(3)
    battery = ["".join(rnd.choice("ab '\"\\ \t#-/=:.+") for _ in range(rnd.randint(0, 9))) for _ in range(3000)]
    r = subprocess.run(["node", "--input-type=module", "-e",
                        f"import fs from 'node:fs'; import {{shellWord}} from '{GZCOORD_MJS}'; "
                        "process.stdout.write(JSON.stringify(JSON.parse(fs.readFileSync(0, 'utf8')).map(shellWord)))"],
                       input=json.dumps(battery), capture_output=True, text=True, timeout=60)
    node = json.loads(r.stdout) if r.returncode == 0 else None
    differ = [(b, n, cg.shell_word(b)) for b, n in zip(battery, node or []) if cg.shell_word(b) != n]
    check("shell_word is Node's shellWord on 3000 lines of quotes, escapes and punctuation", node is not None and not differ,
          differ[:4] or r.stderr[-300:])

    print("gzcoord.test.mjs: api, apiTimeoutMs")
    seen = []

    class Relay(http.server.BaseHTTPRequestHandler):
        def _any(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n).decode() if n else ""
            seen.append({"url": self.path, "method": self.command, "auth": self.headers.get("Authorization"),
                         "type": self.headers.get("Content-Type"), "body": body})
            if self.path == "/refused":
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")
                return
            if self.path == "/silent":
                time.sleep(3)   # the connection held, no answer within the caller's bound
                return
            if self.path == "/trickle":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                for c in b'{"ok":true}':
                    self.wfile.write(bytes([c]))
                    self.wfile.flush()
                    time.sleep(0.15)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())

        do_GET = do_POST = _any

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Relay)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    relay_url = f"http://127.0.0.1:{server.server_port}"
    try:
        check("a POST sends its JSON and answers JSON",
              cg.api("tok", "/api/x?a=1", relay_url=relay_url, method="POST", body='{"k":1}') == {"ok": True})
        check("...with the bearer token and the JSON type",
              seen[0] == {"url": "/api/x?a=1", "method": "POST", "auth": "Bearer tok", "type": "application/json", "body": '{"k":1}'},
              seen[0])
        try:
            cg.api("tok", "/refused", relay_url=relay_url)
            check("a refusal throws with its status", False)
        except cg.ApiError as e:
            check("a refusal throws with its status", e.status == 401 and str(e) == "/refused -> HTTP 401" and not e.timed_out, (e.status, str(e)))
        for bound, said in ((0.2, "0.2"), (0.2005, "0.2005")):
            t0 = time.monotonic()
            try:
                cg.api("tok", "/silent", relay_url=relay_url, timeout_s=bound)
                check(f"a silent relay times out within {bound} s", False)
            except cg.ApiError as e:
                check(f"a silent relay is no answer within {said} s, never a hang",
                      e.timed_out is True and e.status is None and str(e) == f"/silent -> no answer within {said} s"
                      and time.monotonic() - t0 < 2, (str(e), e.timed_out, time.monotonic() - t0))
        t0 = time.monotonic()
        try:
            cg.api("tok", "/trickle", relay_url=relay_url, timeout_s=0.5)
            check("a relay that trickles its body is held to the bound", False)
        except cg.ApiError as e:
            check("a relay that trickles its body is held to the bound, body included",
                  e.timed_out is True and time.monotonic() - t0 < 2, time.monotonic() - t0)
        check("the bound outlasts the wait a long poll asks",
              cg.api_timeout_s("/api/messages?channel=c") == cg.API_TIMEOUT_S
              and cg.api_timeout_s("/api/wait?channel=c&timeout_seconds=55") == cg.API_TIMEOUT_S + 55
              and cg.api_timeout_s("/api/wait?timeout_seconds=nope") == cg.API_TIMEOUT_S)
        probe = ["/api/messages?channel=c", "/api/wait?channel=c&timeout_seconds=55", "/api/wait?timeout_seconds=nope",
                 "/x?timeout_seconds=-5", "/x?timeout_seconds=1e3", "/x?timeout_seconds=", "/x?timeout_seconds=%2010",
                 "/x?timeout_seconds=Infinity", "/x?timeout_seconds=3&timeout_seconds=9", "/x"]
        r = subprocess.run(["node", "--input-type=module", "-e",
                            f"import fs from 'node:fs'; import {{apiTimeoutMs}} from '{GZCOORD_MJS}'; "
                            "process.stdout.write(JSON.stringify(JSON.parse(fs.readFileSync(0, 'utf8')).map(apiTimeoutMs)))"],
                           input=json.dumps(probe), capture_output=True, text=True, timeout=60)
        node = json.loads(r.stdout) if r.returncode == 0 else r.stderr[-300:]
        mine = [cg.api_timeout_s(p) * 1000 for p in probe]
        check("api_timeout_s is Node's apiTimeoutMs / 1000 on every shape of query", mine == node, (mine, node))
        try:
            cg.api("tok\nX-Evil: 1", "/api/x", relay_url=relay_url)
            check("a token holding a line break is refused", False)
        except tokens.TokenRefused as e:
            check("a token holding a line break is refused, naming none of it", "Evil" not in str(e) and "tok\n" not in str(e), str(e))
    finally:
        server.shutdown()
        server.server_close()

    print("gzcoord.test.mjs: relayFailure")
    check("no answer", cg.relay_failure(cg.ApiError("/api/send -> no answer within 30 s", timed_out=True), "http://r")
          == "the relay at http://r did not answer (no answer within 30 s)")
    check("a refusal", cg.relay_failure(cg.ApiError("x", status=503), "http://r") == "the relay refused (HTTP 503)")
    check("a caller's own timeout is no answer too",
          cg.relay_failure(TimeoutError("x"), "http://r") == "the relay at http://r did not answer within the caller's bound")
    check("no connection", cg.relay_failure(cg.ApiError("/x -> [Errno 111] Connection refused"), "http://r")
          == "the relay is unreachable at http://r")

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
