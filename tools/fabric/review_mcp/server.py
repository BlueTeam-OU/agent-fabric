#!/usr/bin/env python3
"""fabric-review — the review class's read tools and its sandboxed checks (agent-fabric ADR-065 §2 A and B), over MCP stdio.

    bin/fabric-review-mcp            stdio, started by Claude Code from the review class's agent file

CONTRACT
  transport  newline-delimited JSON-RPC 2.0 on stdin/stdout, one message per line (MCP stdio), as memory_mcp (ADR-049); stderr is a log.
  methods    initialize, notifications/initialized (no answer), ping, tools/list, tools/call. Anything else is -32601 for a request
             and silence for a notification. A line that is not JSON is -32700 with id null.
  tools      review_diff, review_log, review_show, review_blame, review_grep (gittools.py) and review_check (sandbox.py). A tool's own
             refusal or failure is a result with isError true and one line, never a JSON-RPC error: the model reads results.
  arguments  typed fields; nothing is a command line. A field that starts with "-" is refused; a revision is resolved by git and only
             the commit id it gave is used; the repository is the session clone (CLAUDE_PROJECT_DIR's toplevel) or one of its worktrees.
  children   no shell; git with config that names a program overridden; every child in the review guard's CLEAN_ENV (scope.py), a byte
             cap that the result says it reached, a wall budget, and its whole process group ended on expiry (runner.py).
  writes     none: no tool names a verb that writes, fetches or moves a ref, and review_check runs where nothing it can reach is writable.
  exit       0 at end of input.
"""
from __future__ import annotations

import json
import os
import sys

sys.dont_write_bytecode = True   # before the imports below: a server run from an install tree leaves no __pycache__ in it (as subagent-clone-guard.py)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from review_mcp import gittools, sandbox, scope  # noqa: E402

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "fabric-review", "version": "1"}

_S = {"type": "string"}
_REPO = {"repository": {**_S, "description": "the session clone or one of its worktrees; the clone when absent"}}
_PATHSPEC = {"pathspec": {"type": ["string", "array"], "items": _S, "description": "paths or globs, no leading \":\""}}
_CAP = f"Output is cut at {gittools.CAP_BYTES} bytes and the result says so."


def _tool(function, description: str, properties: dict, required: list[str]):
    return function, description + " " + _CAP, {**_REPO, **properties}, required


def tool_table(box: sandbox.Sandbox) -> dict:
    return {
        "review_diff": _tool(lambda a: gittools.review_diff(a), "git diff between two commits.", {
            "base": _S, "head": _S, **_PATHSPEC, "context": {"type": "integer"},
            "output": {**_S, "enum": ["patch", "stat", "name-only", "name-status"]}}, ["base", "head"]),
        "review_log": _tool(lambda a: gittools.review_log(a), "git log of a commit, or of base..head, optionally of one path.", {
            "head": _S, "base": _S, "path": _S, "max_count": {"type": "integer"}, "patch": {"type": "boolean"}}, ["head"]),
        "review_show": _tool(lambda a: gittools.review_show(a), "git show of a commit, or of one file at a commit when path is given.", {
            "rev": _S, "path": _S}, ["rev"]),
        "review_blame": _tool(lambda a: gittools.review_blame(a), "git blame of a line span of one file at a commit.", {
            "rev": _S, "path": _S, "line_start": {"type": "integer"}, "line_end": {"type": "integer"}}, ["rev", "path", "line_start"]),
        "review_grep": _tool(lambda a: gittools.review_grep(a), "git grep of a commit (extended regex, or fixed text with fixed).", {
            "rev": _S, "pattern": _S, **_PATHSPEC, "fixed": {"type": "boolean"}, "ignore_case": {"type": "boolean"},
            "max_count": {"type": "integer"}}, ["rev", "pattern"]),
        "review_check": _tool(box.check, "Run one program with its arguments (an argv, not a shell line) over the head worktree in a "
                              "read-only sandbox with no network and a scratch /tmp; a check that must write elsewhere fails and is not run.", {
            "head": _S, "argv": {"type": "array", "items": _S}, "timeout_s": {"type": "integer"}}, ["head", "argv"]),
    }


class Server:
    def __init__(self) -> None:
        self.tools = tool_table(sandbox.Sandbox())

    def call(self, name: str, args: object) -> dict:
        entry = self.tools.get(name)
        if entry is None:
            return _result(f"unknown tool {name}", error=True)
        if not isinstance(args, dict):
            return _result("arguments must be an object", error=True)
        try:
            return _result(entry[0](args))
        except scope.ToolError as e:
            return _result(str(e), error=True)

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
                for n, (_f, desc, props, req) in self.tools.items()]})
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
    return serve(Server())


if __name__ == "__main__":
    sys.exit(main())
