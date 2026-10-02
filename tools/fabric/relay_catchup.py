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
that refused or did not answer, no token, or a control channel named
(refused, never acknowledged).
"""
from __future__ import annotations

import os
import pwd
import socket
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relay import TOKEN_NAME, call as _call, channels, is_control, own_token, records  # noqa: E402


def catch_up(relay: str, channel: str, consumer: str, tok: str) -> int | None:
    """Acknowledge the newest message on the channel as this consumer: the
    seq the cursor now stands at, or None for an empty channel. The relay
    lists its newest page, oldest first."""
    page = _call(relay, tok, "/api/messages?" + urllib.parse.urlencode({"channel": channel, "limit": "50"}))
    msgs = records(page)
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
    try:
        pairs, none = channels(argv, os.environ)
    except ValueError as e:
        print(f"relay-catchup: {e}", file=sys.stderr)
        return 1
    for p in none:
        print(f"relay-catchup: {p} has no GZCoord integration; no channel to catch up on")
    rc = 0
    for relay, channel in pairs:
        # The control channel carries the fleet's signed operations, never a
        # session's messages: an acknowledgement there would move this
        # account's cursor on it (inbox.mjs and send.mjs refuse it too).
        if is_control(channel):
            print(f"relay-catchup: {channel} is the control channel; not acknowledged there", file=sys.stderr)
            rc = 1
            continue
        try:
            seq = catch_up(relay, channel, consumer, tok)
        except (OSError, ValueError, KeyError, TypeError) as e:
            # urllib's errors are OSErrors; the message names the status, never
            # the token. A malformed answer (a page that is not a list of
            # objects) is a TypeError: said too, never a traceback.
            print(f"relay-catchup: {channel} at {relay}: {e}", file=sys.stderr)
            rc = 1
            continue
        print(f"relay-catchup: {consumer} on {channel}: "
              + (f"cursor at seq {seq}; what came before is marked read" if seq is not None else "no message yet"))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
