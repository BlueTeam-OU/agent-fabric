#!/usr/bin/env python3
"""tools/fabric/relay_catchup.py — a new account starts with its GZCoord
cursor at the channel's newest message, not at the relay's first.

    relay_catchup.py <project>...

Run AS THE ACCOUNT, by new-agent.sh once its store is synced. The relay
keeps one cursor per consumer and channel, moved only forward by an
acknowledgement; a consumer it has never seen reads from the first message
it holds, which for the fleet's channel was over ten thousand when
python-dev-01 and rust-ui-dev-01 were made (2026-10-01). Everything before
the account existed is someone else's history: acknowledging the newest
message marks it read, and the account's first session sees only what
comes after.

Each project's integration (projects/<id>/integration/gzcoord/config.json)
names its relay and channel, as communication/gzcoord/scripts/inbox.mjs
reads them; CLAUDE_BRIDGE_URL and GZCOORD_CHANNEL override them there and
here. The token is the account's own, from the file `fabric-secrets sync`
writes; it is read in this process and never printed. A project with no
integration has no channel to catch up on, and is said.

exit 0 every channel caught up (or empty, or no integration); 1 a relay
that refused or did not answer, or no token.
"""
from __future__ import annotations

import json
import os
import pwd
import shlex
import socket
import sys
import urllib.parse
import urllib.request

FABRIC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN_NAME = "CLAUDE_BRIDGE_AUTH_TOKEN"


def channels(projects: list[str], env: dict[str, str]) -> tuple[list[tuple[str, str]], list[str]]:
    """(relay, channel) pairs, once each, and the projects with no integration."""
    seen, none = [], []
    for p in projects:
        path = os.path.join(FABRIC, "projects", p, "integration", "gzcoord", "config.json")
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
        except FileNotFoundError:
            none.append(p)
            continue
        pair = (env.get("CLAUDE_BRIDGE_URL") or cfg["relay_url"], env.get("GZCOORD_CHANNEL") or cfg["channel"])
        if pair not in seen:
            seen.append(pair)
    return seen, none


def own_token(home: str) -> str | None:
    try:
        with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), encoding="utf-8") as f:
            for line in f:
                if line.startswith(f"export {TOKEN_NAME}="):
                    return (shlex.split(line.split("=", 1)[1]) or [None])[0]
    except OSError:
        return None
    return None


def _call(relay: str, tok: str, path: str, body: dict | None = None):
    req = urllib.request.Request(relay + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def catch_up(relay: str, channel: str, consumer: str, tok: str) -> int | None:
    """Acknowledge the newest message on the channel as this consumer: the
    seq the cursor now stands at, or None for an empty channel. The relay
    lists its newest page, oldest first."""
    page = _call(relay, tok, "/api/messages?" + urllib.parse.urlencode({"channel": channel, "limit": "50"}))
    msgs = page.get("messages", []) if isinstance(page, dict) else page
    if not msgs:
        return None
    newest = max(msgs, key=lambda m: int(m["seq"]))
    _call(relay, tok, "/api/ack", {"consumer_id": consumer, "channel": channel, "message_id": newest["id"]})
    return int(newest["seq"])


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    me = pwd.getpwuid(os.getuid())
    tok = own_token(os.environ.get("HOME") or me.pw_dir)
    if not tok:
        print(f"relay-catchup: no {TOKEN_NAME} in this account's secrets.env (fabric-secrets sync first)", file=sys.stderr)
        return 1
    consumer = f"{socket.gethostname().split('.')[0]}/{me.pw_name}"
    pairs, none = channels(argv, os.environ)
    for p in none:
        print(f"relay-catchup: {p} has no GZCoord integration; no channel to catch up on")
    rc = 0
    for relay, channel in pairs:
        try:
            seq = catch_up(relay, channel, consumer, tok)
        except (OSError, ValueError, KeyError) as e:
            # urllib's errors are OSErrors; the message names the status, never the token.
            print(f"relay-catchup: {channel} at {relay}: {e}", file=sys.stderr)
            rc = 1
            continue
        print(f"relay-catchup: {consumer} on {channel}: "
              + (f"cursor at seq {seq}; what came before is marked read" if seq is not None else "no message yet"))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
