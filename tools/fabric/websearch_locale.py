#!/usr/bin/env python3
"""tools/fabric/websearch_locale.py — web search located in a login's locale, as an MCP server on stdio, over two
engines. Ported from runtime/mcp/websearch-locale/server.mjs (agent-fabric ADR-040, off Node); the tools, their
arguments and their replies are the Node server's, recorded as tests/fixtures/websearch-locale-parity.json before the
Node was deleted.

    bin/fabric-websearch-locale        stdio, started by Claude Code from the login's ~/.claude.json

WHY. Claude Code's own WebSearch takes a query and two domain lists and is US-only; Anthropic's `user_location` is on
the Messages API and the harness does not expose it. So a language-culture holder, who must search as a reader of its
locale would, gets this server: one tool per engine the locale file configures
(identities/roles/language-culture/locale/<suffix>/locale.json, kept by the CEO: "keep both engines"):

  web_search         the engines in order, SerpAPI (Google's results, with `gl`, `hl` and where the file names them
                     `google_domain` and `lr` fixed from the file), then Brave when SerpAPI refused — its 250 a month
                     spent or anything else — the first that answers wins, and the result's last line names the engine
                     by the file's `label` for it (in the locale, no vendor: the CEO, 2026-09-17) and, after a
                     fall-back, why. Secret SERPAPI_API_KEY: SerpAPI takes it only as the `api_key` query parameter,
                     so this is the one request whose URL carries a secret; the URL is built per call and never
                     logged or returned.
  web_search_global  Brave alone (`country` from the file, ALL for a locale Brave lacks — it has no Georgian — and
                     search_lang / ui_lang only where the file names them). Secret BRAVE_SEARCH_API_KEY, in one header.

CONTRACT
  env      WEBSEARCH_LOCALE_FILE (required: the locale file decides the country and language); HOME for the synced
           secrets file (~/.config/agent-fabric/secrets.env, `export NAME=<shell word>`, first match wins), then the
           environment of the same name. Read at each call, never at start: a sync lands without a restart.
  stdin    newline-delimited JSON-RPC 2.0: initialize (the client's protocolVersion echoed, 2024-11-05 if none),
           notifications/* (no answer), ping, tools/list, tools/call; anything else -32601, an invalid message -32600,
           a line that is not JSON -32700 with a null id.
  tools    arguments {query: string of at least two characters (UTF-16 units, as the Node counted), count: 1-20,
           clamped, default 10}. A bad query is -32602; a failed search is a result with isError true and a line a
           reader can act on, never a secret.
  stdout   one JSON line per answer, UTF-8, compact.
  failure  a search that fails for any reason is a result with isError true; a message whose handling raises something
           nobody foresaw is a JSON-RPC -32603 that names no cause (a URL carries a key); the server does not end.
  stderr   nothing, but the one line `websearch-locale: <why>` before exit 1 when the locale file cannot be read.
  secrets  never in a URL but SerpAPI's own, a log line, a result or an error; a key that cannot be a header value
           (a control character) is refused without being quoted.
  network  https only to the two API hosts, no environment proxy (a credential would go through it), a redirect
           followed only within its own origin (httpsafe.py); 20 s a request.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import shlex
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import httpsafe  # noqa: E402

SERPAPI_URL = "https://serpapi.com/search.json"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
SECRETS = {"serpapi": ["SERPAPI_API_KEY"], "brave": ["BRAVE_SEARCH_API_KEY"]}
REQUIRED = {"serpapi": ["gl", "hl", "tool_description"], "brave": ["country", "tool_description"]}
ORDER = ["serpapi", "brave"]
TIMEOUT_S = 20
# JavaScript's \s: the Node replaced runs of these in a snippet, and Python's set is another.
_JS_SPACE = re.compile("[\t\n\v\f\r    -     　﻿]+")
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
_FORM_SAFE = frozenset(b"*-._0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")

# A response, as the transport hands it up: (HTTP status, body text). The transport raises TimeoutError for no answer
# and OSError for no connection; the Node server's two words for them.
Fetch = Callable[[str, dict[str, str]], tuple[int, str]]


class LocaleError(Exception):
    """The locale file cannot decide the search: said once, then exit 1."""


def _configured(locale: Mapping[str, Any], engine: str) -> bool:
    """JavaScript's truthiness of the block: an empty object is present (and then refused for its missing fields), as
    the Node server had it; null, false, 0 and "" are absent."""
    block = locale.get(engine)
    return block is not None and block is not False and block != 0 and block != ""


def read_locale(file: str | None = None) -> dict[str, Any]:
    file = os.environ.get("WEBSEARCH_LOCALE_FILE") if file is None else file
    if not file:
        raise LocaleError("WEBSEARCH_LOCALE_FILE is not set: the locale file decides the country and language")
    try:
        with open(file, encoding="utf-8") as fh:
            locale = json.load(fh)
    except (OSError, ValueError) as e:
        raise LocaleError(f"{file}: {e.strerror if isinstance(e, OSError) and e.strerror else e}") from None
    if not isinstance(locale, dict):
        raise LocaleError(f"locale file {file}: not an object")
    engines = [e for e in REQUIRED if _configured(locale, e)]
    if not engines:
        raise LocaleError(f"locale file {file}: no engine configured (serpapi, brave)")
    for e in engines:
        block = locale[e]
        for k in REQUIRED[e]:
            if not isinstance(block, dict) or not isinstance(block.get(k), str) or not block[k]:
                raise LocaleError(f"locale file {file}: {e}.{k} missing")
    return locale


def _quote(text: str) -> str:
    """URLSearchParams' serialisation: space is +, everything but *-._ and ASCII alphanumerics is percent-encoded."""
    out = []
    for b in text.encode("utf-8", "replace"):
        out.append(chr(b) if b in _FORM_SAFE else "+" if b == 0x20 else f"%{b:02X}")
    return "".join(out)


def _count(value: object) -> str:
    """String(Math.min(20, Math.max(1, Number(count) || 10))): NaN and 0 are the default, a fraction stays one, an
    integer too large for a float is Infinity (clamped), and anything that is not a number or a numeric string is NaN."""
    if isinstance(value, bool):
        n = float(value)
    elif isinstance(value, (int, float)):
        try:
            n = float(value)
        except OverflowError:
            n = float("inf") if value > 0 else float("-inf")
    elif isinstance(value, str):
        try:
            n = float(value.strip() or 0)
        except ValueError:
            n = float("nan")
    elif value is None:
        n = 0.0
    else:
        n = float("nan")
    if n != n or n == 0:
        n = 10.0
    n = min(20.0, max(1.0, n))
    return str(int(n)) if n == int(n) else repr(n)


def request(engine: str, query: str, locale: Mapping[str, Any], count: object = None,
            secrets: Mapping[str, str] | None = None) -> str:
    """The URL per engine, both GETs with the parameters in it. SerpAPI's `api_key` is the secret itself (its only
    auth), added here from `secrets` and nowhere else; Brave's key rides in a header."""
    secrets = secrets or {}
    if engine == "serpapi":
        p = locale["serpapi"]
        params = [("engine", "google"), ("q", query), ("gl", p["gl"]), ("hl", p["hl"])]
        if p.get("google_domain"):
            params.append(("google_domain", p["google_domain"]))
        if p.get("lr"):
            params.append(("lr", p["lr"]))
        params.append(("num", _count(count)))
        if secrets.get("SERPAPI_API_KEY"):
            params.append(("api_key", secrets["SERPAPI_API_KEY"]))
        base = SERPAPI_URL
    else:
        b = locale["brave"]
        params = [("q", query), ("country", b["country"])]
        if b.get("search_lang"):
            params.append(("search_lang", b["search_lang"]))
        if b.get("ui_lang"):
            params.append(("ui_lang", b["ui_lang"]))
        params.append(("count", _count(count)))
        base = BRAVE_URL
    return base + "?" + "&".join(f"{_quote(k)}={_quote(v)}" for k, v in params)


def synced_var(name: str, home: str | None = None) -> str | None:
    """`export NAME=<shell word>` from the synced secrets file, the first line that names it: the word as shlex reads
    it, None for an empty or unterminated one, never a guess."""
    home = home or os.path.expanduser("~")
    prefix = f"export {name}="
    try:
        with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), encoding="utf-8") as fh:
            for line in fh.read().split("\n"):
                if not line.startswith(prefix):
                    continue
                try:
                    words = shlex.split(line[len(prefix):])
                except ValueError:
                    return None
                return words[0] if words and words[0] else None
    except (OSError, UnicodeDecodeError):
        pass       # not enrolled, or no sync yet
    return None


def secrets_of(engine: str, environ: Mapping[str, str] | None = None) -> dict[str, str | None]:
    environ = os.environ if environ is None else environ
    out: dict[str, str | None] = {}
    for n in SECRETS[engine]:
        value = synced_var(n)
        out[n] = environ.get(n) if value is None else value
    return out


def search_opener() -> urllib.request.OpenerDirector:
    """No environment proxy (a key would go through it) and a redirect only within its own origin."""
    return httpsafe.opener(proxies=False, redirects="same-origin")


def http_fetch(url: str, headers: dict[str, str]) -> tuple[int, str]:
    # A key in the URL or a header goes to its own host and nowhere else (httpsafe.py).
    opener = search_opener()
    try:
        with opener.open(urllib.request.Request(url, headers=headers, method="GET"), timeout=TIMEOUT_S) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "replace")
        finally:
            e.close()
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise TimeoutError from None
        raise OSError from None
    except http.client.HTTPException:
        # A reply cut off mid-body or with a status line that is not HTTP: the connection failed, as Node's fetch said.
        raise OSError from None
    except ValueError:
        # http.client quotes the whole offending header in this error: a key with it.
        raise OSError from None


def _js(value: object) -> str:
    """A value in a JS template literal, for the shapes an API answers: null and undefined are '', a boolean its word."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def strip_tags(text: object) -> str:
    """A description's markup (tag-shaped spans only, so "a < b" prose stays) removed until none is left: one pass over
    "<<b>b>" leaves "<b>", and a stray angle bracket is dropped too. The text reaches a model, not a browser. Bounded:
    a description is a few hundred bytes and each pass is linear, so 16 passes and 4 kB cap a crafted "<b<b<b…>>>"
    (review of #39)."""
    # slice(0, 4096) counts UTF-16 units, as JavaScript does; a cut through a surrogate pair leaves the lone half. serve()
    # writes it as U+FFFD. That is a departure from Node, whose JSON.stringify wrote the escape \\ud83d: a lone surrogate
    # in a JSON line is not valid UTF-8 text, and a reader that takes the line as text should not meet one.
    s = ("null" if text is None else _js(text)).encode("utf-16-le", "surrogatepass")[:8192].decode("utf-16-le", "surrogatepass")
    for _ in range(16):
        prev = s
        s = _TAG.sub("", s)
        if s == prev:
            break
    return s.replace("<", "").replace(">", "")


def _clip(text: str, units: int) -> str:
    """slice(0, n) of a JavaScript string: UTF-16 units, so a cut through a surrogate pair leaves the lone half."""
    return text.encode("utf-16-le", "surrogatepass")[: units * 2].decode("utf-16-le", "surrogatepass")


def _get(obj: object, *path: str) -> object:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def search(engine: str, query: str, locale: Mapping[str, Any], secrets: Mapping[str, str | None] | None = None,
           fetch: Fetch = http_fetch, count: object = None) -> dict[str, Any]:
    """One search on one engine: the results as text, one block each — title, link, snippet — or an error the
    caller can read, never a secret."""
    secrets = secrets_of(engine) if secrets is None else secrets
    missing = next((n for n in SECRETS[engine] if not secrets.get(n)), None)
    if missing:
        return {"isError": True, "text": f"no {missing} in the synced secrets: fabric-secrets sync, after it is in the store of this login"}
    url = request(engine, query, locale, count, {k: v for k, v in secrets.items() if v})
    headers = {"Accept": "application/json"}
    if engine == "brave":
        key = secrets["BRAVE_SEARCH_API_KEY"]
        if not key.isascii() or any(ord(c) < 0x20 or ord(c) == 0x7F for c in key):
            return {"isError": True, "text": "search failed: BRAVE_SEARCH_API_KEY cannot be a header value (a control or non-ASCII character)"}
        headers["X-Subscription-Token"] = key
    try:
        status, body = fetch(url, headers)
    except TimeoutError:
        return {"isError": True, "text": "search failed: timeout"}
    except OSError:
        return {"isError": True, "text": "search failed: unreachable"}
    try:
        j: object = json.loads(body)
        parsed = True
    except ValueError:
        j, parsed = None, False
    if not 200 <= status < 300:
        why = ""
        if parsed:
            err = _get(j, "error")
            why = err if isinstance(err, str) else next((v for v in (_get(j, "message"), _get(err, "message"), _get(err, "detail"))
                                                        if v is not None), "")
        return {"isError": True, "text": f"search refused: HTTP {status}" + (f" — {_clip(_js(why), 200)}" if why else "")}
    if not parsed:
        return {"isError": True, "text": "search answered something that is not JSON"}
    if engine == "serpapi" and _get(j, "error"):
        return {"isError": True, "text": f"search refused: {_clip(_js(_get(j, 'error')), 200)}"}
    if engine == "serpapi":
        rows = _get(j, "organic_results")
        items = [(_get(x, "title"), _get(x, "link"), _get(x, "snippet")) for x in rows] if isinstance(rows, list) else []
    else:
        rows = _get(j, "web", "results")
        items = [(_get(x, "title"), _get(x, "url"), strip_tags(_js(_get(x, "description")))) for x in rows] if isinstance(rows, list) else []
    if not items:
        return {"isError": False, "text": f"no results ({engine})"}
    return {"isError": False, "text": "\n\n".join(
        f"{i}. {_js(t)}\n   {_js(link)}\n   {_JS_SPACE.sub(' ', _js(d))}" for i, (t, link, d) in enumerate(items, 1))}


def search_with_fallback(engines: list[str], query: str, locale: Mapping[str, Any], secrets: Mapping[str, Any] | None = None,
                         fetch: Fetch = http_fetch, count: object = None) -> dict[str, Any]:
    """The engines in order; the first that answers wins, and the last line names it by the file's label, and why the
    ones before it did not."""
    refused: list[str] = []

    def label(e: str) -> str:
        block = locale.get(e)
        return (block.get("label") if isinstance(block, dict) else None) or e
    for engine in engines:
        r = search(engine, query, locale, None if secrets is None else (secrets.get(engine) or {}), fetch, count)
        if not r["isError"]:
            return {"isError": False, "text": f"{r['text']}\n\n— {label(engine)}" + (f" ({'; '.join(refused)})" if refused else "")}
        refused.append(f"{label(engine)}: {r['text']}")
    return {"isError": True, "text": "; ".join(refused)}


def tools(locale: Mapping[str, Any]) -> list[dict[str, Any]]:
    schema = {"type": "object", "additionalProperties": False, "required": ["query"],
              "properties": {"query": {"type": "string", "minLength": 2}, "count": {"type": "integer", "minimum": 1, "maximum": 20}}}
    out = []
    first = next((e for e in ORDER if _configured(locale, e)), None)
    if first:
        out.append({"name": "web_search", "description": locale[first]["tool_description"], "inputSchema": schema})
    if _configured(locale, "brave"):
        out.append({"name": "web_search_global", "description": locale["brave"]["tool_description"], "inputSchema": schema})
    return out


def _units(text: str) -> int:
    """JavaScript's string length: UTF-16 code units."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def handle(msg: object, locale: Mapping[str, Any], secrets: Mapping[str, Any] | None = None, fetch: Fetch = http_fetch) -> dict | None:
    """The answer to one message, or None when it needs none. A request that carries no id is answered without one,
    as JSON.stringify dropped an undefined id."""
    def reply(result: object) -> dict:
        out: dict[str, Any] = {"jsonrpc": "2.0"}
        if isinstance(msg, dict) and "id" in msg:
            out["id"] = msg["id"]
        out["result"] = result
        return out

    def error(code: int, message: str) -> dict:
        ident = msg.get("id") if isinstance(msg, dict) else None
        return {"jsonrpc": "2.0", "id": None if ident is None else ident, "error": {"code": code, "message": message}}
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return error(-32600, "invalid request")
    method = msg["method"]
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        version = params.get("protocolVersion")
        return reply({"protocolVersion": "2024-11-05" if version is None else version, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "websearch-locale", "version": "1"}})
    if method == "ping":
        return reply({})
    if method == "tools/list":
        return reply({"tools": tools(locale)})
    if method == "tools/call":
        name = params.get("name")
        if name == "web_search":
            engines = [e for e in ORDER if _configured(locale, e)]
        elif name == "web_search_global" and _configured(locale, "brave"):
            engines = ["brave"]
        else:
            engines = []
        if not engines:
            return error(-32602, f"unknown tool {_js(name) if name is not None else 'undefined'}")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        q = arguments.get("query")
        if not isinstance(q, str) or _units(q) < 2:
            return error(-32602, "query: a string of at least two characters")
        r = search_with_fallback(engines, q, locale, secrets, fetch, arguments.get("count"))
        return reply({"content": [{"type": "text", "text": r["text"]}], "isError": r["isError"]})
    return error(-32601, f"method not found: {method}")


def _no_constant(name: str) -> object:
    """NaN, Infinity and -Infinity are not JSON: a line carrying one is a parse error, as in Node, and an id of one
    is never echoed as invalid JSON."""
    raise ValueError(name)


def serve(locale: Mapping[str, Any], stdin=None, stdout=None, secrets: Mapping[str, Any] | None = None, fetch: Fetch = http_fetch) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line, parse_constant=_no_constant)
        except ValueError:
            out: dict | None = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            try:
                out = handle(msg, locale, secrets, fetch)
            except Exception:  # noqa: BLE001 - a search must never end the server; the answer says nothing of the cause
                ident = msg.get("id") if isinstance(msg, dict) else None
                out = {"jsonrpc": "2.0", "id": ident if isinstance(ident, (str, int, float)) and not isinstance(ident, bool) else None,
                       "error": {"code": -32603, "message": "internal error"}}
        if out is not None:
            stdout.write(_LONE_SURROGATE.sub("\ufffd", json.dumps(out, ensure_ascii=False, separators=(",", ":"))) + "\n")
            stdout.flush()
    return 0


def main() -> int:
    # UTF-8 whatever the locale of the login, and a lone surrogate from a JSON string is a ?, not a crash mid-run.
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        locale = read_locale()
    except LocaleError as e:
        print(f"websearch-locale: {e}", file=sys.stderr)
        return 1
    return serve(locale)


if __name__ == "__main__":
    sys.exit(main())
