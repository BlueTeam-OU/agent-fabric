#!/usr/bin/env python3
"""tools/fabric/websearch_locale.py (bin/fabric-websearch-locale), the Python port of the locale search MCP server.
The Node server's answers on 313 cases — every request URL, search result, MCP reply and stripped description — were
recorded to tests/fixtures/websearch-locale-parity.json before it was deleted, and are replayed here (the parity
run of ADR-040 §5 rule 5); what the Node tests asserted is ported case for case below the replay. Plain script:
prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import http.client  # noqa: F401 - http.client is the library the transport uses
import http.server
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import websearch_locale as ws  # noqa: E402

BIN = os.path.join(HERE, "bin", "fabric-websearch-locale")
FIXTURE = os.path.join(HERE, "tests", "fixtures", "websearch-locale-parity.json")
LOCALE = {"timezone": "Asia/Tbilisi",
          "serpapi": {"gl": "ge", "hl": "ka", "google_domain": "google.ge", "tool_description": "ვებ-ძიება ქართულად", "label": "ძირითადი ძრავა"},
          "brave": {"country": "ALL", "tool_description": "გლობალური ვებ-ძიება"}}
G = {"SERPAPI_API_KEY": "serpapi-secret-key-value-0123456789"}
B = {"BRAVE_SEARCH_API_KEY": "BSA-secret-key-value-0123456789"}


def fake_fetch(spec: dict):
    def fetch(url: str, headers: dict) -> tuple[int, str]:
        if spec.get("throw") == "TimeoutError":
            raise TimeoutError
        if spec.get("throw"):
            raise OSError
        return spec["status"], spec["body"]
    return fetch


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with open(FIXTURE, encoding="utf-8") as fh:
        data = json.load(fh)
    locales, specs = data["locales"], data["specs"]

    print("parity with the recorded Node answers")
    wrong: dict[str, list[str]] = {}
    for c in data["cases"]:
        kind = c["kind"]
        if kind == "request":
            count = None if isinstance(c["count"], dict) else c["count"]
            got = ws.request(c["engine"], c["query"], locales[c["locale"]], count, c["secrets"])
        elif kind == "search":
            got = ws.search(c["engine"], c["query"], locales[c["locale"]], c["secrets"], fake_fetch(specs[c["spec"]]))
        elif kind == "handle":
            def fetch(url: str, headers: dict, c=c) -> tuple[int, str]:
                return fake_fetch(specs[c["map"].get("serpapi" if "serpapi" in url else "brave", c["map"].get("any"))])(url, headers)
            got = ws.handle(c["msg"], locales[c["locale"]], c["secrets"], fetch)
        else:
            got = ws.strip_tags(c["input"])
        want = c["expected"]
        # JSON.stringify of the Node's answer is what was recorded: compare as the wire would carry them.
        if json.dumps(got, ensure_ascii=False, sort_keys=True) != json.dumps(want, ensure_ascii=False, sort_keys=True):
            wrong.setdefault(kind, []).append(f"{c.get('name') or c.get('spec') or c.get('input')!r:.60}: got {got!r:.200} want {want!r:.200}")
    for kind in ("request", "search", "handle", "strip"):
        n = sum(1 for c in data["cases"] if c["kind"] == kind)
        check(f"{n} {kind} cases answer as the Node did", not wrong.get(kind), "\n".join(wrong.get(kind, [])[:6]))

    print("the locale file")
    with tempfile.TemporaryDirectory() as t:
        def locale_file(doc, name="locale.json") -> str:
            path = os.path.join(t, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(doc if isinstance(doc, str) else json.dumps(doc))
            return path

        def why(doc) -> str:
            try:
                ws.read_locale(locale_file(doc))
                return ""
            except ws.LocaleError as e:
                return str(e)
        check("a complete locale reads as it is written", ws.read_locale(locale_file(LOCALE)) == LOCALE)
        check("an engine block with a field missing", "serpapi.hl missing" in why({"serpapi": {**LOCALE["serpapi"], "hl": ""}}))
        check("a locale with no engine", "no engine configured" in why({"timezone": "x"}))
        check("one engine alone is fine", list(ws.read_locale(locale_file({"timezone": "x", "brave": LOCALE["brave"]}))) == ["timezone", "brave"])
        try:
            ws.read_locale("")
            named = ""
        except ws.LocaleError as e:
            named = str(e)
        check("WEBSEARCH_LOCALE_FILE unset is said", named.startswith("WEBSEARCH_LOCALE_FILE is not set"), named)
        check("a file that is not JSON, one that is not an object, one that is not there: said, never a traceback",
              all(why(d) for d in ("{ nope", "[1]", "null")) and why("{ nope") != "")
        try:
            ws.read_locale(os.path.join(t, "absent.json"))
            absent = ""
        except ws.LocaleError as e:
            absent = str(e)
        check("…the absent one names the file", "absent.json" in absent, absent)

        print("the secrets")
        home = os.path.join(t, "home")
        os.makedirs(os.path.join(home, ".config", "agent-fabric"))
        env = os.path.join(home, ".config", "agent-fabric", "secrets.env")

        def synced(text: str, name: str = "K") -> str | None:
            with open(env, "w", encoding="utf-8") as fh:
                fh.write(text)
            return ws.synced_var(name, home)
        check("a plain word", synced("export K=abc\n") == "abc")
        check("single-quoted, with the shell's own escape of a quote", synced("export K='a'\"'\"'b'\n") == "a'b")
        check("double-quoted with an escaped quote", synced('export K="a\\"b"\n') == 'a"b')
        check("the first line that names it wins", synced("export K=one\nexport K=two\n") == "one")
        check("a name that is only a prefix of another is not it", synced("export KK=x\n") is None)
        check("an empty value is none; an unterminated quote is none, never a guess", synced("export K=\n") is None and synced("export K='abc\n") is None)
        check("a file that is not there is none", ws.synced_var("K", os.path.join(t, "nobody")) is None)
        with open(env, "w", encoding="utf-8") as fh:
            fh.write("export SERPAPI_API_KEY=fromfile\n")
        saved = {k: os.environ.get(k) for k in ("HOME", "SERPAPI_API_KEY", "BRAVE_SEARCH_API_KEY")}
        os.environ.update(HOME=home, SERPAPI_API_KEY="fromenv", BRAVE_SEARCH_API_KEY="braveenv")
        try:
            check("the synced file first, the environment when it names none",
                  ws.secrets_of("serpapi") == {"SERPAPI_API_KEY": "fromfile"} and ws.secrets_of("brave") == {"BRAVE_SEARCH_API_KEY": "braveenv"})
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        print("what reaches the wire")
        seen: list = []

        def recording(spec):
            def fetch(url, headers):
                seen.append((url, headers))
                return spec["status"], spec["body"]
            return fetch
        ws.search("serpapi", "q", LOCALE, G, recording(specs["serpOk"]))
        ws.search("brave", "q", LOCALE, B, recording(specs["braveOk"]))
        check("SerpAPI's key is its api_key and nothing but Accept is sent", "api_key=" + G["SERPAPI_API_KEY"] in seen[0][0] and list(seen[0][1]) == ["Accept"])
        check("Brave's key is in one header and not in the URL", seen[1][1].get("X-Subscription-Token") == B["BRAVE_SEARCH_API_KEY"]
              and B["BRAVE_SEARCH_API_KEY"] not in seen[1][0])
        results = [ws.search("serpapi", "q", LOCALE, G, fake_fetch(specs["serpOk"])), ws.search("brave", "q", LOCALE, B, fake_fetch(specs["braveOk"])),
                   ws.search("serpapi", "q", LOCALE, G, fake_fetch(specs["serp401"]))]
        check("no secret in a result or an error", not any(v in json.dumps(r) for r in results for v in (*G.values(), *B.values())))
        for bad in ("key\nvalue", "key\r\nX-Evil: 1", "kéy", "key\x00"):
            r = ws.search("brave", "q", LOCALE, {"BRAVE_SEARCH_API_KEY": bad}, recording(specs["braveOk"]))
            check(f"a Brave key that cannot be a header value ({bad!r:.14}) is refused and not quoted",
                  r["isError"] and "cannot be a header value" in r["text"] and bad not in r["text"] and len(seen) == 2, str(r))

        print("the transport")
        hits: list = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 — the stdlib's name
                hits.append((self.path, dict(self.headers)))
                if self.path.startswith("/same"):
                    self.send_response(302)
                    self.send_header("Location", "http://127.0.0.1:%d/landed" % self.server.server_port)
                    self.end_headers()
                    return
                if self.path.startswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", "http://localhost:%d/landed" % self.server.server_port)
                    self.end_headers()
                    return
                body = json.dumps({"organic_results": [{"title": "t", "link": "l", "snippet": "s"}]}).encode()
                self.send_response(200 if not self.path.startswith("/err") else 429)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body if not self.path.startswith("/err") else b'{"error":"spent"}')

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_port}"
        os.environ["http_proxy"] = os.environ["https_proxy"] = "http://127.0.0.1:9"       # a proxy that would refuse: it must not be consulted
        try:
            status, body = ws.http_fetch(base + "/ok?q=1", {"Accept": "application/json", "X-Subscription-Token": "tok"})
            check("a 200 comes back with its body; the headers reach the host; the environment's proxy is not used",
                  status == 200 and "organic_results" in body and hits[-1][1].get("X-Subscription-Token") == "tok", str((status, hits[-1:])))
            check("a 429 is a status, not an exception", ws.http_fetch(base + "/err", {})[0] == 429)
            check("a redirect within the origin is followed (what fetch did)", ws.http_fetch(base + "/same", {})[0] == 200 and hits[-1][0] == "/landed")
            before = len(hits)
            status, _ = ws.http_fetch(base + "/redirect", {"X-Subscription-Token": "tok"})
            check("a redirect to another origin is not followed (the key goes to its own host only)",
                  status == 302 and [p for p, _ in hits[before:]] == ["/redirect"], str(hits[before:]))
        finally:
            os.environ.pop("http_proxy", None)
            os.environ.pop("https_proxy", None)
            srv.shutdown()
        try:
            ws.http_fetch("http://127.0.0.1:9/", {})
            refused = ""
        except OSError as e:
            refused = type(e).__name__
        check("no connection is OSError, which the search says as unreachable", refused != "")
        try:
            ws.http_fetch(base + "/x", {"X-Subscription-Token": "a\nb"})
            quoted = ""
        except OSError as e:
            quoted = str(e)
        check("a header value http.client refuses never surfaces with the value quoted", "a\nb" not in quoted and "\\n" not in quoted, quoted)

        print("what Node answered and a bare exception would not")

        def one_shot(reply: bytes):
            srv_ = socket.socket()
            srv_.bind(("127.0.0.1", 0))
            srv_.listen(1)

            def go():
                c, _ = srv_.accept()
                c.recv(4096)
                c.sendall(reply)
                c.close()
                srv_.close()
            threading.Thread(target=go, daemon=True).start()
            return f"http://127.0.0.1:{srv_.getsockname()[1]}/"
        for label, reply in (("a reply cut off mid-body", b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\n\r\n{\"a\":"),
                             ("a status line that is not HTTP", b"garbage\r\n\r\n")):
            url = one_shot(reply)
            r = ws.search("brave", "ab", LOCALE, B, lambda _u, h, url=url: ws.http_fetch(url, h))
            check(f"{label}: a tool error that says unreachable, not an exception out of the server", r == {"isError": True, "text": "search failed: unreachable"}, str(r))
        check("an integer too large for a float is clamped like Infinity, and a dict or a list is NaN (the default)",
              ws._count(10 ** 400) == "20" and ws._count(-(10 ** 400)) == "1" and ws._count({"a": 1}) == "10" and ws._count([5]) == "10"
              and ws._count(None) == "10" and ws._count("7") == "7" and ws._count(True) == "1")
        sink = io.StringIO()
        boom = lambda _u, _h: (_ for _ in ()).throw(RuntimeError("secret-url-with-key"))  # noqa: E731
        ws.serve(LOCALE, io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "web_search_global", "arguments": {"query": "ab"}}})
                                     + "\n" + json.dumps({"jsonrpc": "2.0", "id": 6, "method": "ping"}) + "\n"), sink, {"brave": B}, boom)
        lines = [json.loads(x) for x in sink.getvalue().splitlines()]
        check("an exception nobody foresaw is a JSON-RPC error that names no cause, and the next message is answered",
              lines[0]["error"]["code"] == -32603 and "secret" not in sink.getvalue() and lines[1] == {"jsonrpc": "2.0", "id": 6, "result": {}}, sink.getvalue())
        sink = io.StringIO()
        ws.serve(LOCALE, io.StringIO('{"jsonrpc":"2.0","id":NaN,"method":"ping"}\n{"jsonrpc":"2.0","id":Infinity,"method":"ping"}\n'), sink)
        check("NaN and Infinity in a line are a parse error, never echoed as invalid JSON",
              [json.loads(x)["error"]["code"] for x in sink.getvalue().splitlines()] == [-32700, -32700] and "NaN" not in sink.getvalue())
        emoji = "😀" * 150
        long_err = ws.search("brave", "ab", LOCALE, B, lambda _u, _h: (500, json.dumps({"message": emoji})))
        check("an error body is cut at 200 UTF-16 units, as Node cut it", long_err["text"] == "search refused: HTTP 500 — " + "😀" * 100, long_err["text"][:60])
        for label, doc, expect in (("an empty engine block is refused for its missing fields, not dropped", {"serpapi": {}, "brave": LOCALE["brave"]}, "serpapi.gl missing"),
                                   ("…a null block is absent", {"serpapi": None, "brave": LOCALE["brave"]}, "")):
            f = os.path.join(t, "empty-block.json")
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            try:
                ws.read_locale(f)
                got = ""
            except ws.LocaleError as e:
                got = str(e)
            check(label, (expect in got) if expect else got == "", got)

        os.environ["https_proxy"] = "http://127.0.0.1:9"
        try:
            def proxies_of(**kw) -> list[dict]:
                return [h.proxies for h in ws.httpsafe.opener(redirects="same-origin", **kw).handlers if hasattr(h, "proxies")]
            used = [h.proxies for h in ws.search_opener().handlers if hasattr(h, "proxies")]
            check("with https_proxy in the environment, the opener the search uses holds no proxy (a key would go through it)", used == [], str(used))
            check("…and the same environment does give the other policy one (the positive control)", proxies_of(proxies=True) == [{"https": "http://127.0.0.1:9"}],
                  str(proxies_of(proxies=True)))
        finally:
            os.environ.pop("https_proxy", None)

        print("stripTags")
        t0 = time.monotonic()
        ws.strip_tags("<b" * 50000 + ">" * 50000)
        check("a crafted nesting is bounded, not quadratic", time.monotonic() - t0 < 1.0)
        check("at most 16 passes: a deeper nesting leaves residue rather than looping", len(ws.strip_tags("<b" * 20 + ">" * 20)) > 0)

        print("the wire, as Node wrote it")
        long_desc = json.dumps({"web": {"results": [{"title": "t", "url": "u", "description": "x" + "😀" * 2100}]}})
        sink = io.StringIO()
        ws.serve(LOCALE, io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                "params": {"name": "web_search_global", "arguments": {"query": "ab"}}}) + "\n"), sink,
                 {"brave": B}, lambda url, headers: (200, long_desc))
        check("a description cut through a surrogate pair is written with U+FFFD, not a ? and not a crash",
              "\ufffd" in sink.getvalue() and "?" not in json.loads(sink.getvalue())["result"]["content"][0]["text"].split("\n")[2], sink.getvalue()[-80:])
        check("the answer is one compact line, non-ASCII raw", sink.getvalue().count("\n") == 1 and "\\u" not in sink.getvalue())

        print("the server process, over stdio")
        locale_path = locale_file(LOCALE, "stdio.json")
        proc_home = os.path.join(t, "proc-home")
        os.makedirs(os.path.join(proc_home, ".config", "agent-fabric"))
        with open(os.path.join(proc_home, ".config", "agent-fabric", "secrets.env"), "w", encoding="utf-8") as fh:
            fh.write(f"export GH_TOKEN='{B['BRAVE_SEARCH_API_KEY']}'\n")      # neither search key
        penv = {"PATH": os.environ.get("PATH", ""), "HOME": proc_home, "WEBSEARCH_LOCALE_FILE": locale_path,
                "AGENT_FABRIC_PYTHON": sys.executable, "LC_ALL": "C", "PYTHONIOENCODING": "ascii"}
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "web_search", "arguments": {"query": "მეტრო"}}}]
        r = subprocess.run([BIN], input=("\n".join(json.dumps(m) for m in msgs) + "\nnot json\n").encode(), env=penv, capture_output=True, timeout=60)
        out = [json.loads(ln) for ln in r.stdout.decode("utf-8").splitlines()]
        check("exit 0 at end of input; a locale-C login still gets UTF-8", r.returncode == 0 and "ვებ-ძიება ქართულად".encode() in r.stdout, r.stderr.decode())
        check("initialize, tools/list, a missing secret is a tool error, a bad line is -32700 with a null id",
              out[0]["result"]["serverInfo"]["name"] == "websearch-locale" and [x["name"] for x in out[1]["result"]["tools"]] == ["web_search", "web_search_global"]
              and out[2]["result"]["isError"] is True and "no SERPAPI_API_KEY" in out[2]["result"]["content"][0]["text"]
              and "brave: no BRAVE_SEARCH_API_KEY" in out[2]["result"]["content"][0]["text"] and out[3]["error"]["code"] == -32700 and out[3]["id"] is None, str(out))
        check("no secret on stdout or stderr", B["BRAVE_SEARCH_API_KEY"].encode() not in r.stdout + r.stderr and r.stderr == b"")
        for label, content, want in (("unset", None, "WEBSEARCH_LOCALE_FILE is not set"), ("not JSON", "{ nope", "stdio-bad.json")):
            e2 = dict(penv)
            if content is None:
                e2.pop("WEBSEARCH_LOCALE_FILE")
            else:
                e2["WEBSEARCH_LOCALE_FILE"] = locale_file(content, "stdio-bad.json")
            r = subprocess.run([BIN], input=b"", env=e2, capture_output=True, timeout=60)
            check(f"a locale file that is {label}: one line on stderr, exit 1, no traceback",
                  r.returncode == 1 and r.stdout == b"" and r.stderr.decode().startswith("websearch-locale: ") and want in r.stderr.decode()
                  and r.stderr.count(b"\n") == 1, r.stderr.decode())

    print("test_websearch_locale:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
