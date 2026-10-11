#!/usr/bin/env python3
"""runtime/mcp/fabric-memory/install.py — the fabric-memory MCP entry in a login's Claude Code user configuration
(ADR-049 §5 rule 1).

    install.py <claude.json> set [--dry-run]

`set` writes (or leaves, when identical) mcpServers["fabric-memory"] as a stdio server whose command is the bare
name `fabric-memory-mcp` on PATH (the ~/.local/bin link every bin/ command has, ADR-040 §5 rule 7), never a bin/
path. Every other key and server of the file is kept as read; the file is replaced atomically with its mode kept
(0600 when it is created). An entry of that name whose command is not ours is the login's own and is left as it is.
Prints one line in the installer's shape (+ = !) and exits 0.

A file that is not JSON, or whose top level is not an object, is the login's to fix: one line on stderr, nothing
written, exit 1. Unlike the websearch-locale installer there is no `remove`: the server is for every login.
"""
from __future__ import annotations

import json
import os
import sys

NAME = "fabric-memory"
COMMAND = "fabric-memory-mcp"
ENTRY = {"type": "stdio", "command": COMMAND, "args": [], "env": {}}


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("top level is not an object")
    return data


def save(path: str, data: dict) -> None:
    tmp = f"{path}.agent-fabric.tmp"
    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        mode = 0o600   # holds the login's other servers' keys
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def ours(entry: object) -> bool:
    return isinstance(entry, dict) and entry.get("command") == COMMAND


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    if len(argv) != 2 or argv[1] != "set":
        print(__doc__, file=sys.stderr)
        return 2
    path = argv[0]
    try:
        data = load(path)
    except (ValueError, UnicodeDecodeError) as e:
        print(f"  !  {path}: not a JSON object ({type(e).__name__}); left alone, nothing written", file=sys.stderr)
        return 1
    servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
    current = servers.get(NAME)
    if current == ENTRY:
        print(f"  =  {path} mcpServers.{NAME}")
        return 0
    if current is not None and not ours(current):
        print(f"  !  {path} mcpServers.{NAME} is not this fabric's; left as is")
        return 0
    if dry:
        print(f"  +  {path} mcpServers.{NAME} (would write)")
        return 0
    servers[NAME] = dict(ENTRY)
    data["mcpServers"] = servers
    save(path, data)
    print(f"  +  {path} mcpServers.{NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
