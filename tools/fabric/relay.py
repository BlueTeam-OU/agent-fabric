#!/usr/bin/env python3
"""tools/fabric/relay.py — the GZCoord relay as an account's own tools reach
it: which relays and channels, its own token, one HTTP GET. A library, not
a command; fabric-status's inbox line (status.py `inbox_state`) reads the
relay through it until the control plane leaves the relay (gate 3, W16),
when this file goes. The journal's import that read it is gone (W15).

Each project's integration (projects/<id>/integration/gzcoord/config.json)
names its relay and channel, as gzcoord-inbox
reads them; CLAUDE_BRIDGE_URL and GZCOORD_CHANNEL override them there and
here. The token is the account's own, from the file `fabric-secrets sync`
writes; a caller reads it in its own process, puts it in a header, and
prints it nowhere — never in a URL, where an error message would carry it.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import httpsafe  # noqa: E402
import roots  # noqa: E402

TOKEN_NAME = "CLAUDE_BRIDGE_AUTH_TOKEN"
TIMEOUT = 30


def config_path(project: str) -> str:
    # A project's integration is the operator's; the checkout the code is in
    # stands in for the operator when none is exported, as this module took
    # its tree from its own location, never AGENT_FABRIC_ROOT.
    return roots.project_integration(project, "gzcoord", "config.json", engine=roots.code_root())


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


def own_token(home: str) -> str | None:
    try:
        with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), encoding="utf-8") as f:
            for line in f:
                if line.startswith(f"export {TOKEN_NAME}="):
                    return (shlex.split(line.split("=", 1)[1]) or [None])[0]
    except OSError:
        return None
    return None


OPENER = httpsafe.opener(proxies=False, redirects="none")


def call(relay: str, tok: str, path: str, timeout: float = TIMEOUT):
    """A GET, whose JSON answer is read. urllib's errors are OSErrors and
    name the status, never the header the token is in.
    The relay is reached directly, never through the environment's proxy,
    and a redirect is an error, never followed with the token (httpsafe)."""
    req = urllib.request.Request(relay + path, headers={"Authorization": f"Bearer {tok}"}, method="GET")
    with OPENER.open(req, timeout=timeout) as r:
        return json.load(r)
