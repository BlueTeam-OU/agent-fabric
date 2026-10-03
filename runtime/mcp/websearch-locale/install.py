#!/usr/bin/env python3
"""runtime/mcp/websearch-locale/install.py — the MCP entry for the locale
search tool in a login's Claude Code user configuration.

    install.py <claude.json> set <server.mjs> <locale.json> [--dry-run]
    install.py <claude.json> remove [--dry-run]
    install.py <settings.json> deny-websearch [--dry-run]
    install.py <settings.json> allow-websearch [--dry-run]

`set` writes (or leaves, when identical) mcpServers["websearch-locale"]
as a stdio server running <server.mjs> with WEBSEARCH_LOCALE_FILE set to
<locale.json>; `remove` deletes an entry that runs this fabric's server —
recognised by the path in its args — and never one the login wrote
itself. `deny-websearch` adds "WebSearch" to permissions.deny in the
login's user settings — the harness's own search is not for a login
that searches through its locale (the launcher removes the tool at exec;
this is the fence for a session launched otherwise) — and records that
the fabric did, in permissions.deny's sibling marker
"WebSearch # agent-fabric"; `allow-websearch` removes both, and never a
"WebSearch" the login denied itself (no marker). Prints one line in the
installer's shape (+ = -) and exits 0. Both files are Claude Code's own:
every other key is kept as read.

A file that is not JSON is the login's to fix, and is left alone: one
line on stderr, then exit 0 for `remove` and `allow-websearch` (nothing
of the fabric's can be in force in a file the harness cannot read
either) and 1 for `set` and `deny-websearch` (theirs is not written).
It once raised here, and bootstrap ended in a traceback before the user
settings' own writer could refuse the file.
"""
from __future__ import annotations

import json
import os
import sys

NAME = "websearch-locale"
MARKER = "runtime/mcp/websearch-locale/server.mjs"
DENY = "WebSearch"
# The record that the fabric wrote the deny: a second entry the harness
# reads as a rule that matches nothing, beside the real one.
DENY_MARK = "WebSearch(agent-fabric)"


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def save(path: str, data: dict) -> None:
    tmp = f"{path}.agent-fabric.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def ours(entry: object) -> bool:
    return isinstance(entry, dict) and any(MARKER in str(a) for a in entry.get("args", []))


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    path, op = argv[0], argv[1]
    try:
        data = load(path)
    except (ValueError, UnicodeDecodeError) as e:
        undo = op in ("remove", "allow-websearch")
        print(f"  !  {path}: not JSON ({type(e).__name__}); left alone, "
              + ("nothing of the fabric's to remove" if undo else "nothing written"), file=sys.stderr)
        return 0 if undo else 1
    servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
    current = servers.get(NAME)
    if op == "set":
        server, locale = argv[2], argv[3]
        want = {"type": "stdio", "command": "node", "args": [server], "env": {"WEBSEARCH_LOCALE_FILE": locale}}
        if current == want:
            print(f"  =  {path} mcpServers.{NAME}")
            return 0
        if current is not None and not ours(current):
            print(f"  !  {path} mcpServers.{NAME} is not this fabric's; left as is")
            return 0
        if dry:
            print(f"  +  {path} mcpServers.{NAME} (would write)")
            return 0
        servers[NAME] = want
        data["mcpServers"] = servers
        save(path, data)
        print(f"  +  {path} mcpServers.{NAME}")
        return 0
    if op == "remove":
        if current is None or not ours(current):
            return 0
        if dry:
            print(f"  -  {path} mcpServers.{NAME} (would remove: not a language-culture login with a locale)")
            return 0
        del servers[NAME]
        data["mcpServers"] = servers
        save(path, data)
        print(f"  -  {path} mcpServers.{NAME} (removed: not a language-culture login with a locale)")
        return 0
    if op in ("deny-websearch", "allow-websearch"):
        perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
        deny = list(perms.get("deny") or []) if isinstance(perms.get("deny"), list) else []
        mine = DENY_MARK in deny
        if op == "deny-websearch":
            if DENY in deny and mine:
                print(f"  =  {path} permissions.deny {DENY}")
                return 0
            if dry:
                print(f"  +  {path} permissions.deny {DENY} (would write)")
                return 0
            for entry in (DENY, DENY_MARK):
                if entry not in deny:
                    deny.append(entry)
        else:
            if not mine:
                return 0   # not denied, or denied by the login itself: left alone
            if dry:
                print(f"  -  {path} permissions.deny {DENY} (would remove: not a language-culture login with a locale)")
                return 0
            deny = [e for e in deny if e not in (DENY, DENY_MARK)]
        perms["deny"] = deny
        data["permissions"] = perms
        save(path, data)
        sign = "+" if op == "deny-websearch" else "-"
        print(f"  {sign}  {path} permissions.deny {DENY}" + ("" if sign == "+" else " (removed: not a language-culture login with a locale)"))
        return 0
    print(f"install.py: unknown op {op}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
