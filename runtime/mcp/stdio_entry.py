"""runtime/mcp/stdio_entry.py — the shared part of the installers that put one of the fabric's own stdio MCP servers
into a login's Claude Code user configuration (runtime/mcp/fabric-memory/install.py, runtime/mcp/fabric-review/
install.py; ADR-049 §5 rule 1, ADR-065 §2 A).

An installer is `install.py <claude.json> set [--dry-run]`, and calls `main(argv, name, command, doc)`: it writes (or
leaves, when identical) mcpServers[name] as a stdio server whose command is the bare name `command` on PATH (the
~/.local/bin link every bin/ command has, ADR-040 §5 rule 7), never a bin/ path. Every other key and server of the
file is kept as read; the file is replaced atomically with its mode kept (0600 when it is created). An entry of that
name whose command is not ours is the login's own and is left as it is. Prints one line in the installer's shape
(+ = !) and exits 0.

A file that is not JSON, whose top level is not an object, whose mcpServers is present and not an object, or that
cannot be read (mode 000, a directory), is the login's to fix: one line on stderr, nothing written, exit UNUSABLE
(3: distinct from Python's 1, which any uncaught fault such as an unwritable directory exits with, so a caller can
tell the login's file from a fault).
"""
from __future__ import annotations

import contextlib
import json
import os
import sys

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


def main(argv: list[str], name: str, command: str, doc: str) -> int:
    entry = {"type": "stdio", "command": command, "args": [], "env": {}}
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    if len(argv) != 2 or argv[1] != "set":
        print(doc, file=sys.stderr)
        return 2
    path = argv[0]
    try:
        data = load(path)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        # OSError: mode 000, a directory. An unreadable file is the login's to fix like a malformed one, and must
        # not end bootstrap in a traceback (install_agent_files.mcp_entry reads 3 as "not configured").
        why = f"unreadable ({e.strerror or type(e).__name__})" if isinstance(e, OSError) else f"unusable ({e or type(e).__name__})"
        print(f"  !  {path}: {why}; left alone, nothing written", file=sys.stderr)
        return UNUSABLE
    servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
    current = servers.get(name)
    if current == entry:
        print(f"  =  {path} mcpServers.{name}")
        return 0
    if current is not None and not (isinstance(current, dict) and current.get("command") == command):
        print(f"  !  {path} mcpServers.{name} is not this fabric's; left as is")
        return 0
    if dry:
        print(f"  +  {path} mcpServers.{name} (would write)")
        return 0
    servers[name] = dict(entry)
    data["mcpServers"] = servers
    save(path, data)
    print(f"  +  {path} mcpServers.{name}")
    return 0
