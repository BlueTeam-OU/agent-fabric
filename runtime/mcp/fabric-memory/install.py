#!/usr/bin/env python3
"""runtime/mcp/fabric-memory/install.py — the fabric-memory MCP entry in a login's Claude Code user configuration
(ADR-049 §5 rule 1).

    install.py <claude.json> set [--dry-run]

`set` writes (or leaves, when identical) mcpServers["fabric-memory"] as a stdio server whose command is the bare
name `fabric-memory-mcp` on PATH (the ~/.local/bin link every bin/ command has, ADR-040 §5 rule 7), never a bin/
path. Every other key and server of the file is kept as read; the file is replaced atomically with its mode kept
(0600 when it is created). An entry of that name whose command is not ours is the login's own and is left as it is.
Prints one line in the installer's shape (+ = !) and exits 0.

A file that is not JSON, whose top level is not an object, or whose mcpServers is present and not an object, is the login's to fix: one line on stderr, nothing
written, exit 3 (UNUSABLE: distinct from Python's 1, which any uncaught
fault such as an unwritable directory exits with, so a caller can tell the login's file from a fault). Unlike the websearch-locale installer there is no `remove`: the server is for every login.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys

NAME = "fabric-memory"
COMMAND = "fabric-memory-mcp"
ENTRY = {"type": "stdio", "command": COMMAND, "args": [], "env": {}}



UNUSABLE = 3   # the file is the login's to fix; nothing written. Never 1, which an uncaught fault exits with.

def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("top level is not an object")
    if "mcpServers" in data and not isinstance(data["mcpServers"], dict):
        raise ValueError("mcpServers is not an object")     # replacing it would drop whatever the login put there
    return data


def save(path: str, data: dict) -> None:
    tmp = f"{path}.agent-fabric.{os.getpid()}.tmp"      # per process: two installs must not rename each other's half file
    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        mode = 0o600   # holds the login's other servers' keys
    # Created 0600, never wider: the file holds the login's other servers' keys, and a umask-default create would
    # expose them until the chmod below.
    # A stale temp under this pid (a killed run, the pid reused) is removed, never written through: O_EXCL with
    # O_NOFOLLOW creates a fresh file or fails, so a leftover's mode or a symlink at the name is never inherited.
    with contextlib.suppress(FileNotFoundError):
        os.unlink(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


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
        print(f"  !  {path}: unusable ({e or type(e).__name__}); left alone, nothing written", file=sys.stderr)
        return UNUSABLE
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
