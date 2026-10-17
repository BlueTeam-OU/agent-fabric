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

        print("the holder's search country (ADR-060 rule 8): exported by the launcher, never read from the store")
        lf = locale_file(LOCALE, "country.json")

        def gl(environ: dict) -> str:
            return ws.request("serpapi", "q", ws.read_locale(lf, environ)).split("gl=")[1].split("&")[0]
        check("no export: the locale file's country answers", gl({}) == "ge")
        check("…an empty export too (the launcher drops what nobody names; empty is not a country)", gl({"AGENT_FABRIC_SEARCH_COUNTRY": ""}) == "ge")
        check("an export replaces SerpAPI's gl", gl({"AGENT_FABRIC_SEARCH_COUNTRY": "us"}) == "us")
        check("…and only gl: Brave's country and the other fields are the file's",
              ws.read_locale(lf, {"AGENT_FABRIC_SEARCH_COUNTRY": "us"})["brave"] == LOCALE["brave"]
              and ws.read_locale(lf, {"AGENT_FABRIC_SEARCH_COUNTRY": "us"})["serpapi"]["hl"] == "ka")
        replaced = ws.read_locale(lf, {"AGENT_FABRIC_SEARCH_COUNTRY": "us"})
        check("…and a read after it, without the export, is the file's again (nothing carried over)",
              replaced["serpapi"]["gl"] == "us" and ws.read_locale(lf, {})["serpapi"]["gl"] == "ge")
        for bad in ("US", "usa", "u", "1a", " us"):
            try:
                ws.read_locale(lf, {"AGENT_FABRIC_SEARCH_COUNTRY": bad})
                named = ""
            except ws.LocaleError as e:
                named = str(e)
            check(f"a malformed export {bad!r} is refused by name, not read as the file's", "AGENT_FABRIC_SEARCH_COUNTRY" in named, named)
        brave_only = locale_file({"brave": LOCALE["brave"]}, "brave-only.json")
        check("a locale with Brave alone has no gl to replace: the export changes nothing",
              ws.read_locale(brave_only, {"AGENT_FABRIC_SEARCH_COUNTRY": "us"}) == {"brave": LOCALE["brave"]})

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
        check("the first word is the value: a stray quote later in the line does not lose it; one in the first word still does",
              synced("export K=abc 'def\n") == "abc" and synced("export K=abc # a comment\n") == "abc" and synced("export K='abc def\n") is None)
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
        check("an integer too large for a float is clamped like Infinity, and a dict is NaN (the default)",
              ws._count(10 ** 400) == "20" and ws._count(-(10 ** 400)) == "1" and ws._count({"a": 1}) == "10"
              and ws._count(None) == "10" and ws._count("7") == "7" and ws._count(True) == "1")
        # What Node's Number() made of a count that arrives as a string, recorded from node: Python's float() reads more.
        node_counts = {"7": "7", " 7 ": "7", "1_0": "10", "inf": "10", "Infinity": "20", "-Infinity": "1", "+Infinity": "20", "0x10": "16",
                       "0X1f": "20", "0b11": "3", "0o17": "15", "1e1": "10", "1e": "10", "5.": "5", "  .5": "1", "+5": "5", "-5": "1", "": "10",
                       "  ": "10", "\u00a05\u00a0": "5", "\ufeff5": "5", "0x" + "f" * 300: "20", "5px": "10", "\u0661\u0662": "10", "1,5": "10"}
        off = {k: (ws._count(k), v) for k, v in node_counts.items() if ws._count(k) != v}
        check("a count given as a string is read as JavaScript's Number() reads it (24 spellings recorded from node)", not off, str(off))
        # Node: j?.error is truthy for {} and [], and String() of an object is "[object Object]", of an array its joined items.
        def refused(engine: str, body: dict, status: int = 200) -> str:
            return ws.search(engine, "ab", LOCALE, {"SERPAPI_API_KEY": G["SERPAPI_API_KEY"], **B}, lambda _u, _h: (status, json.dumps(body)))["text"]
        check("a SerpAPI error that is an empty object or array is still a refusal, worded as String() words it",
              refused("serpapi", {"error": {}}) == "search refused: [object Object]" and refused("serpapi", {"error": []}) == "search refused: "
              and refused("serpapi", {"error": [1, None, "a", [2, 3]]}) == "search refused: 1,,a,2,3"
              and refused("serpapi", {"error": 0, "organic_results": []}) == "no results (serpapi)", refused("serpapi", {"error": {}}))
        # Node: why = j.error if a string, else j.message ?? j.error.message ?? j.error.detail ?? ""; and `why ? " — " + why : ""`
        # where an object or array is truthy even when empty. So an empty error object says nothing (why is ""), and an empty or
        # array message says "[object Object]" or nothing after the dash.
        check("an HTTP error whose error object is empty says the status alone, as Node did", refused("brave", {"error": {}}, 500) == "search refused: HTTP 500",
              refused("brave", {"error": {}}, 500))
        check("…a message that is an empty object is truthy: the status, a dash and String() of it; an empty array, the dash and nothing",
              refused("brave", {"message": {}}, 500) == "search refused: HTTP 500 — [object Object]"
              and refused("brave", {"message": []}, 500) == "search refused: HTTP 500 — "
              and refused("brave", {"error": {"detail": [1, [], 2]}}, 500) == "search refused: HTTP 500 — 1,,2", refused("brave", {"message": {}}, 500))
        # The numbers String() writes, recorded from node.
        node_numbers = [(1.0, "1"), (1, "1"), (1.5, "1.5"), (1e21, "1e+21"), (1e22, "1e+22"), (123456789012345680000, "123456789012345680000"),
                        (1e-6, "0.000001"), (1e-7, "1e-7"), (0.000001234, "0.000001234"), (1.5e-7, "1.5e-7"), (-2.5, "-2.5"), (100, "100"), (0, "0"),
                        (12345678901234567890, "12345678901234567000"), (-1e21, "-1e+21"), (0.1, "0.1"), (1e300, "1e+300"), (5e-324, "5e-324")]
        wrong = [(n, ws._js(n), e) for n, e in node_numbers if ws._js(n) != e]
        check("a number in an error text is worded as String() words it (18 values recorded from node)", not wrong, str(wrong))
        nested: list = [1]
        for _ in range(899):
            nested = [nested]
        check("a nested array flattens as Array.prototype.toString does, an empty one as an empty element, and a deep one does not recurse",
              ws._js([[], 1]) == ",1" and ws._js([1, []]) == "1," and ws._js([[], []]) == "," and ws._js([[1], [2]]) == "1,2"
              and ws._js(nested) == "1", ws._js([[], 1]))
        deep = "[" * 480 + "]" * 480
        r = ws.search("serpapi", "ab", LOCALE, G, lambda _u, _h: (200, '{"error": ' + deep + "}"))
        check("a reply nested hundreds deep is a refusal the search reports, not an exception out of it (the fall-back must still run)",
              r["isError"] is True and r["text"].startswith("search refused"), str(r)[:80])
        slow = time.monotonic()
        ws._count("1" + " " * 200000 + "x")
        check("a count with a long run of spaces inside it is read in linear time (a regex trim took seconds)", time.monotonic() - slow < 1.0)
        check("a count that is a hexadecimal, octal or binary integer too large for a float is Infinity, clamped (Node: 20)",
              ws._count("0x" + "f" * 300) == "20" and ws._count("0b" + "1" * 1100) == "20" and ws._count("0o" + "7" * 400) == "20")
        # Recorded from node: Number([5]) is 5, Number(["7"]) 7, Number([[5]]) 5, Number([]) 0 (default 10), Number([1,2]) NaN (default 10).
        check("a count given as an array of one is read as Number() reads it; an empty or longer one is the default",
              (ws._count([5]), ws._count(["7"]), ws._count([[5]]), ws._count([]), ws._count([1, 2]), ws._count([100])) == ("5", "7", "5", "10", "10", "20"))
        check("an integer between 1e300 and the float range is written 1e+305, as Node wrote it, not Infinity", ws._js(10 ** 305) == "1e+305"
              and ws._js(-(10 ** 305)) == "-1e+305" and ws._js(10 ** 400) == "Infinity" and ws._js(-(10 ** 400)) == "-Infinity")
        lab = {"serpapi": {**LOCALE["serpapi"], "label": True}, "brave": {**LOCALE["brave"], "label": []}}
        ok_serp = (200, json.dumps({"organic_results": [{"title": "t", "link": "l", "snippet": "s"}]}))
        got = ws.search_with_fallback(["serpapi"], "ab", lab, {"serpapi": G}, lambda _u, _h: ok_serp)
        check("a label that is not a string is worded as a template literal would word it (true), and an empty array is truthy (empty text)",
              got["text"].endswith("\n\n— true") and ws.search_with_fallback(["brave"], "ab", lab, {"brave": B}, lambda _u, _h: (200, json.dumps({"web": {"results": [{"title": "t", "url": "u"}]}})))["text"].endswith("\n\n— "),
              got["text"])
        sink4 = io.StringIO()
        ws.serve(LOCALE, io.StringIO('{"jsonrpc":"2.0","id":1e400,"method":"ping"}\n{"jsonrpc":"2.0","id":2,"method":"initialize","params":{"protocolVersion":[1e400]}}\n'
                                     '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":null}}\n{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{}}\n'), sink4)
        answers = [json.loads(x) for x in sink4.getvalue().splitlines()]
        check("an id or a protocolVersion out of the float range is null on the wire (valid JSON), a tool name of null is worded null and a missing one undefined",
              answers[0] == {"jsonrpc": "2.0", "id": None, "result": {}} and answers[1]["result"]["protocolVersion"] == [None]
              and answers[2]["error"]["message"] == "unknown tool null" and answers[3]["error"]["message"] == "unknown tool undefined" and "Infinity" not in sink4.getvalue(),
              sink4.getvalue())
        sink3 = io.StringIO()
        ws.serve(LOCALE, io.StringIO("\ufeff" + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\u00a0\n"
                                     + "\x1c" + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}) + "\n"), sink3)
        check("a line is trimmed of JavaScript's whitespace (a byte-order mark, a no-break space) and of nothing else (a file separator is not)",
              [json.loads(x).get("result", json.loads(x).get("error", {}).get("code")) for x in sink3.getvalue().splitlines()] == [{}, -32700], sink3.getvalue())
        bom = ws.search("brave", "ab", LOCALE, B, lambda _u, _h: (200, "\ufeff" + json.dumps({"web": {"results": [{"title": "t", "url": "u"}]}})))
        check("a reply that opens with a byte-order mark is JSON (fetch's json() strips it)", bom["isError"] is False)
        sink = io.StringIO()
        boom = lambda _u, _h: (_ for _ in ()).throw(RuntimeError("secret-url-with-key"))  # noqa: E731
        ws.serve(LOCALE, io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "web_search_global", "arguments": {"query": "ab"}}})
                                     + "\n" + json.dumps({"jsonrpc": "2.0", "id": 6, "method": "ping"}) + "\n"), sink, {"brave": B}, boom)
        lines = [json.loads(x) for x in sink.getvalue().splitlines()]
        check("an exception nobody foresaw is a JSON-RPC error that names no cause, and the next message is answered",
              lines[0]["error"]["code"] == -32603 and "secret" not in sink.getvalue() and lines[1] == {"jsonrpc": "2.0", "id": 6, "result": {}}, sink.getvalue())
        sink = io.StringIO()
        ws.serve(LOCALE, io.StringIO('{"jsonrpc":"2.0","id":NaN,"method":"ping"}\n{"jsonrpc":"2.0","id":Infinity,"method":"ping"}\n'), sink)
        sink2 = io.StringIO()
        ws.serve(LOCALE, io.StringIO("[" * 200000 + "\n" + json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n"), sink2)
        check("a line nested past the parser's depth is a parse error and the server goes on to the next message",
              [json.loads(x).get("error", {}).get("code", "ok") if "error" in x else "ok" for x in sink2.getvalue().splitlines()] == [-32700, "ok"], sink2.getvalue()[:120])
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
            fh.write("export GH_TOKEN='decoy-gh-value-not-a-key'\n")      # neither search key
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
        check("nothing of the secrets file on stdout or stderr", b"decoy-gh-value" not in r.stdout + r.stderr and r.stderr == b"")
        ping = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        r = subprocess.run([BIN], input=(ping + "\r" + ping + "\n").encode(), env=penv, capture_output=True, timeout=60)
        out = [json.loads(ln) for ln in r.stdout.decode().splitlines()]
        check("a lone carriage return does not end a message (Node split on the line feed alone): one line, one parse error",
              len(out) == 1 and out[0]["error"]["code"] == -32700, r.stdout.decode())
        r = subprocess.run([BIN], input=(ping + "\r\n").encode() + b"\xff\xfe\n" + (ping + "\n").encode(), env=penv, capture_output=True, timeout=60)
        out = [json.loads(ln) for ln in r.stdout.decode().splitlines()]
        check("a CRLF-ended message is read; bytes that are not UTF-8 are one parse error and the next message is answered",
              r.returncode == 0 and [o.get("result", o.get("error", {}).get("code")) for o in out] == [{}, -32700, {}], r.stdout.decode() + r.stderr.decode())
        absent = dict(penv, AGENT_FABRIC_PYTHON=os.path.join(t, "no-such-python"))
        r = subprocess.run([BIN], input=b"", env=absent, capture_output=True, timeout=60)
        check("a host without the pinned Python: exit 127 and one line that says how to install it, nothing on stdout (the risk of the re-install)",
              r.returncode == 127 and r.stdout == b"" and b"fleet's pinned Python is not installed" in r.stderr and b"python_pin.py install" in r.stderr
              and r.stderr.count(b"\n") == 1, r.stderr.decode())
        r = subprocess.run([BIN], input=b"", env=dict(penv, AGENT_FABRIC_SEARCH_COUNTRY="USA"), capture_output=True, timeout=60)
        check("the server process: a malformed AGENT_FABRIC_SEARCH_COUNTRY is one line on stderr and exit 1; "
              "a well-formed one starts it (positive control)",
              r.returncode == 1 and r.stdout == b"" and b"AGENT_FABRIC_SEARCH_COUNTRY" in r.stderr and r.stderr.count(b"\n") == 1
              and subprocess.run([BIN], input=b"", env=dict(penv, AGENT_FABRIC_SEARCH_COUNTRY="us"), capture_output=True, timeout=60).returncode == 0,
              r.stderr.decode())
        link = os.path.join(t, "linked-websearch")
        os.symlink(BIN, link)
        r = subprocess.run([link], input=(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n").encode(), env=penv, capture_output=True, timeout=60)
        check("started through a symlink, it still finds its module", r.returncode == 0 and json.loads(r.stdout) == {"jsonrpc": "2.0", "id": 1, "result": {}}, r.stderr.decode())
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
