"""tools/fabric/gzcoord/inbox_parts/tokens.py — the relay token, and who this login is to the relay.
A part of tools/fabric/gzcoord/inbox.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
import re
import socket
from .. import gzmsg
from ..gzmsg import en
from .config import relay_runtime_dir, integration_config


def synced_var(name: str, home: str | None = None) -> str | None:
    """One `export NAME=value` line of the synced secrets file, unquoted, or
    None. The value is a secret: printed nowhere, used in place."""
    home = os.path.expanduser("~") if home is None else home
    try:
        with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return None
    pattern = re.compile(f"^export {re.escape(name)}=(.*)$")
    for line in lines:
        m = pattern.match(line)
        if not m:
            continue
        v = gzmsg.js_trim(m.group(1))
        if len(v) >= 2 and ((v[0] == "'" and v[-1] == "'") or (v[0] == '"' and v[-1] == '"')):
            v = v[1:-1]
        elif v in ("'", '"'):
            v = ""   # a lone quote: starts and ends with itself, sliced away
        return v or None
    return None


class TokenRefused(Exception):
    """The relay token holds a line break or a NUL. Said in one line that
    names no part of it."""


def checked_token(v: str | None) -> str | None:
    """Every token leaves this module through here: trimmed of HTTP
    whitespace, as fetch's Headers trimmed a header value, and refused with
    a CR, LF or NUL inside. Such a token reached presence.mjs whole, and the
    first line of its fetch error, carrying the token's start, was printed
    as the presence detail (review of #93, round 2)."""
    if v is None:
        return None
    v = v.strip(" \t\r\n")
    if any(c in v for c in "\r\n\0"):
        raise TokenRefused("the relay token holds a line break or a NUL; nothing was sent with it "
                           "(fabric-secrets sync writes it again)")
    return v


def synced_token(home: str | None = None) -> str | None:
    return checked_token(synced_var("CLAUDE_BRIDGE_AUTH_TOKEN", home))


def token(root: str, cfg: dict | None = None) -> str | None:
    """The token, from wherever this working copy keeps it; never printed,
    never logged. The synced file first: the environment is a snapshot of
    it taken when the session's shell started, and after a rotation it
    stays wrong for the life of the session (web-dev-01, 2026-09-14)."""
    return checked_token(_token(root, cfg))


def _token(root: str, cfg: dict | None) -> str | None:
    # Fields only: nothing this default says is printed.
    cfg = integration_config(None, os.environ, en()) if cfg is None else cfg
    synced = synced_var("CLAUDE_BRIDGE_AUTH_TOKEN")
    if synced:
        return synced
    if os.environ.get("CLAUDE_BRIDGE_AUTH_TOKEN"):
        return os.environ["CLAUDE_BRIDGE_AUTH_TOKEN"]
    env_file = os.path.join(root, cfg["token_env_file"]) if cfg.get("token_env_file") else None
    if env_file and os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as fh:
            for line in fh.read().split("\n"):
                if line.startswith("CLAUDE_BRIDGE_AUTH_TOKEN="):
                    return gzmsg.js_trim(line[len("CLAUDE_BRIDGE_AUTH_TOKEN="):])
    try:
        with open(os.path.join(root, ".claude/settings.local.json"), encoding="utf-8") as fh:
            v = (json.load(fh).get("env") or {}).get("CLAUDE_BRIDGE_AUTH_TOKEN")
        if v:
            return v
    except (OSError, ValueError, AttributeError):
        pass
    # The hosting workspace holds the token the relay itself reads
    # (projects/.gzcoord/bridge-token, 0600): a session there is the host.
    try:
        with open(os.path.join(relay_runtime_dir(cfg), "bridge-token"), encoding="utf-8") as fh:
            v = gzmsg.js_trim(fh.read())
        if v:
            return v
    except OSError:
        pass
    return None


def identity(me: dict | None = None, taxonomy: gzmsg.Taxonomy | None = None) -> dict:
    """Who this session is on the channel: <host>/<login> — the AGENT, never
    the working copy — and the role: the binding's, else a slug the login
    carries. A binding naming a role the catalogue lacks falls back to the
    login's, and the error travels with the identity (review of #55)."""
    me = gzmsg.whoami() if me is None else me
    instance = me["agent"]
    host = me.get("host") if me.get("host") is not None else socket.gethostname().split(".")[0]
    recorded = gzmsg.recorded_role(taxonomy, me) if taxonomy is not None else {"role": None}
    slug = recorded["role"] if recorded.get("role") is not None else \
        (gzmsg.slug_of(instance, taxonomy) if taxonomy is not None else None)
    out = {"address": f"{host}/{instance}", "instance": instance, "slug": slug, "project": me.get("project")}
    if recorded.get("error"):
        out["roleError"] = recorded["error"]
    return out


def for_me(msg: dict, me: dict) -> bool:
    """SPEC §7.1 addressing, SPEC §17 reading rule."""
    m = msg["metadata"]
    if m.get("BROADCAST") == "true":
        return True
    if "TO" in m:
        return m["TO"] == me["address"]
    if "TO-ROLE" in m:
        return me.get("slug") is not None and m["TO-ROLE"] == me["slug"]
    return False
