#!/usr/bin/env python3
"""fabric-memory — the MCP server over the curated memory corpus (agent-fabric ADR-049).

    bin/fabric-memory-mcp            stdio, started by Claude Code from the session's settings

CONTRACT
  transport  newline-delimited JSON-RPC 2.0 on stdin/stdout, one message per line (MCP stdio); stderr is a log.
  methods    initialize, notifications/initialized (no answer), ping, tools/list, tools/call. Anything else is
             -32601 for a request and silence for a notification. A line that is not JSON is -32700 with id null.
  tools      memory_find (ranked one-line hits within max_tokens, each with its band), memory_read (sections by id,
             cut at max_tokens), memory_index, and memory_mark (a verdict on a section, to the login's own
             memory-marks.jsonl; the corpus is never written) (tools.py). The index itself is tools/fabric/memory_index.py. A tool's own failure is a result with isError
             true and one line, never a JSON-RPC error: the model reads results, not protocol errors.
  reads      the fabric's memory/ (roots.py) and the session's working copy's .agent-fabric/memory/ and nothing
             else; writes nothing under either (only the login's state: the call log and the marks); no network, no model.
  state      one line per call in <agent state dir>/memory-calls.jsonl: time, tool, hit count, the ids returned, and for
             a read whether the last find returned one of them; never the query's text (calls.py).
  session    role, project and working copy come from the login's binding; an absent one is "not asked for".
  exit       0 at end of input; the corpus is loaded once at start.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(HERE), os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import identity  # noqa: E402
import roots  # noqa: E402

import memory_index  # noqa: E402
from memory_mcp import calls, tools  # noqa: E402

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "fabric-memory", "version": "1"}


def session_of_binding(state_dir: str) -> tools.Session:
    try:
        with open(os.path.join(state_dir, "binding.json"), encoding="utf-8") as fh:
            binding = json.load(fh)
    except (OSError, ValueError):
        return tools.Session()
    if not isinstance(binding, dict):
        return tools.Session()

    def text(key: str) -> str | None:
        value = binding.get(key)
        return value if isinstance(value, str) and value else None
    return tools.Session(role=text("role"), project=text("project"), working_copy=text("working_copy"), state_dir=state_dir)


class Server:
    def __init__(self, corpus: memory_index.Index, session: tools.Session, state_dir: str) -> None:
        self.corpus, self.session, self.state_dir = corpus, session, state_dir
        self.last_find: set[str] = set()

    def call(self, name: str, args: object) -> dict:
        entry = tools.TOOLS.get(name)
        if entry is None:
            return _result(f"unknown tool {name}", error=True)
        if not isinstance(args, dict):
            return _result("arguments must be an object", error=True)
        try:
            text, ids = entry[0](self.corpus, self.session, args)
        except tools.ToolError as e:
            calls.record(self.state_dir, name, [])
            return _result(str(e), error=True)
        after_find = None
        if name == "memory_find":
            self.last_find = set(ids)
        elif name == "memory_read":
            after_find = bool(self.last_find & set(ids))
        calls.record(self.state_dir, name, ids, after_find)
        return _result(text)

    def handle(self, message: object) -> dict | None:
        """The answer to one message, or None when it needs none."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return _error(message.get("id") if isinstance(message, dict) else None, -32600, "invalid request")
        method, ident, params = message["method"], message.get("id"), message.get("params") or {}
        if "id" not in message:
            return None
        if not isinstance(params, dict):
            return _error(ident, -32602, "params must be an object")
        if method == "initialize":
            wanted = params.get("protocolVersion")
            return _ok(ident, {"protocolVersion": wanted if wanted in PROTOCOLS else PROTOCOLS[0],
                               "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
        if method == "ping":
            return _ok(ident, {})
        if method == "tools/list":
            return _ok(ident, {"tools": [
                {"name": n, "description": desc, "inputSchema": {"type": "object", "properties": props, "required": req}}
                for n, (_f, desc, props, req) in tools.TOOLS.items()]})
        if method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str):
                return _error(ident, -32602, "tools/call needs a tool name")
            return _ok(ident, self.call(name, params.get("arguments") or {}))
        return _error(ident, -32601, f"method not found: {method}")


def _ok(ident: object, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def _error(ident: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}


def _result(text: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": error}


def serve(server: Server, stdin=sys.stdin, stdout=sys.stdout) -> int:
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            answer = _error(None, -32700, "parse error")
        else:
            answer = server.handle(message)
        if answer is not None:
            stdout.write(json.dumps(answer, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0


def main() -> int:
    state_dir = identity.agent_state_dir()
    session = session_of_binding(state_dir)
    corpus = memory_index.build(roots.memory_dir(), session.working_copy)
    return serve(Server(corpus, session, state_dir))


if __name__ == "__main__":
    sys.exit(main())
