#!/usr/bin/env python3
"""tools/fabric/relay.py — the GZCoord relay as an account's own tools reach
it: which relays and channels, its own token, one HTTP call. A library, not
a command; relay_catchup.py and the journal's import (episodic_import.py)
read the relay through it.

Each project's integration (projects/<id>/integration/gzcoord/config.json)
names its relay and channel, as communication/gzcoord/scripts/inbox.mjs
reads them; CLAUDE_BRIDGE_URL and GZCOORD_CHANNEL override them there and
here. The token is the account's own, from the file `fabric-secrets sync`
writes; a caller reads it in its own process, puts it in a header, and
prints it nowhere — never in a URL, where an error message would carry it.
"""
from __future__ import annotations

import json
import os
import shlex
import urllib.parse
import urllib.request

FABRIC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN_NAME = "CLAUDE_BRIDGE_AUTH_TOKEN"
TIMEOUT = 30
# The relay's page bound for a listing (measured on Claude-Bridge 1.3.0,
# docs/live-checks/2026-10-01-episodic-journal.md).
PAGE = 500


def config_path(project: str) -> str:
    return os.path.join(FABRIC, "projects", project, "integration", "gzcoord", "config.json")


def integrated_projects() -> list[str]:
    """Every project the fabric holds a GZCoord integration for."""
    root = os.path.join(FABRIC, "projects")
    return sorted(p for p in os.listdir(root) if os.path.isfile(config_path(p)))


def channels(projects: list[str], env: dict[str, str]) -> tuple[list[tuple[str, str]], list[str]]:
    """(relay, channel) pairs, once each, and the projects with no integration."""
    seen, none = [], []
    for p in projects:
        try:
            with open(config_path(p), encoding="utf-8") as f:
                cfg = json.load(f)
            pair = (env.get("CLAUDE_BRIDGE_URL") or cfg["relay_url"], env.get("GZCOORD_CHANNEL") or cfg["channel"])
        except FileNotFoundError:
            none.append(p)
            continue
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"projects/{p}/integration/gzcoord/config.json is unreadable ({e})") from None
        if pair not in seen:
            seen.append(pair)
    return seen, none


def is_control(channel: str) -> bool:
    """A channel of the fabric's machine records (runtime/control/), never
    GZCOORD/1 messages: no session and no tool of a session's reads it
    (inbox.mjs assertNotControlChannel)."""
    return channel.endswith(":control")


def own_token(home: str) -> str | None:
    try:
        with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), encoding="utf-8") as f:
            for line in f:
                if line.startswith(f"export {TOKEN_NAME}="):
                    return (shlex.split(line.split("=", 1)[1]) or [None])[0]
    except OSError:
        return None
    return None


def call(relay: str, tok: str, path: str, body: dict | None = None, timeout: float = TIMEOUT):
    """GET answers JSON, which is read; a POST's answer is the status alone —
    the ack landed whatever its body says (review of #77). urllib's errors
    are OSErrors and name the status, never the header the token is in."""
    req = urllib.request.Request(relay + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r) if body is None else None


def records(page) -> list:
    """A listing's records: the relay answers {"messages": [...]}, or a bare list."""
    return page.get("messages", []) if isinstance(page, dict) else page


def pages(relay: str, tok: str, channel: str, consumer: str, limit: int = PAGE):
    """Every record on the channel, a page at a time, oldest first. A
    consumer the relay has never seen lists from seq 1; since_id pages
    forward from a record it holds (since_seq is ignored); a listing moves
    no cursor. GET only: nothing is acknowledged, so the consumer is left
    exactly where a listing found it. Ends on an empty page; a page that
    does not move forward is an error, not an endless loop."""
    since, last_seq = None, None
    while True:
        q = {"channel": channel, "consumer_id": consumer, "limit": str(limit), "full": "1"}
        if since is not None:
            q["since_id"] = since
        msgs = records(call(relay, tok, "/api/messages?" + urllib.parse.urlencode(q)))
        if not msgs:
            return
        newest = max(msgs, key=lambda m: int(m["seq"]))
        if last_seq is not None and int(newest["seq"]) <= last_seq:
            raise ValueError(f"the relay's page after seq {last_seq} did not move forward")
        yield msgs
        since, last_seq = newest["id"], int(newest["seq"])
