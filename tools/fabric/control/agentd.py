"""tools/fabric/control/agentd.py — the part of agentd's port that the rest of
the control plane already reaches for: its configuration, the ids it mints,
and the two address sets the registry gives (ADR-040 Wave 8, from
runtime/control/agentd.mjs).

The daemon itself — the accept path, the replay ledger, the main loop and
the unit switch — is the cutover's, sequenced by fabric-coordinator, and is
not here. control/queue.py (control_config, new_id) and control/ctl.py
(control_config, new_id, operator_addresses, account_addresses) import this
module by name; each function is the Node's, byte for byte in what it
returns.

  control_config(env, file)  relay_url, channel, state_channel, ttl_s: the
                             environment, then runtime/control/config.json,
                             then the defaults; `??` kept, so a variable that
                             is set and empty is a value (an empty relay URL
                             names nothing, and the call says so)
  new_id()                   a UUIDv7, the shape gzmsg new-id mints
  operator_addresses(reg)    {<host>/<operator>} for every host; an
                             unreadable registry is nobody
  account_addresses(reg)     {<host>/<login>} for every placement; likewise

An unreadable registry is NOBODY here as in the Node: ctl turns that into a
refusal ("not a host operator"), which is the visible failure.
"""
from __future__ import annotations

import math
import os
from typing import Any

from control import js
from control.gzcoord import FABRIC_ROOT
from gzcoord import gzmsg
import roots

CONFIG = os.path.join(roots.code_root(), "runtime", "control", "config.json")


def number_of(v: Any) -> float:
    """Number(v) for a JSON value."""
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return js.number(js.string(v))


def control_config(env: dict[str, str] | None = None, file: str | None = None) -> dict:
    env = os.environ if env is None else env
    own: Any = {}
    try:
        with open(CONFIG if file is None else file, encoding="utf-8", errors="replace") as fh:
            own = js.json_parse(fh.read())
    except (OSError, ValueError):
        pass   # defaults below
    if not isinstance(own, dict):
        own = {}

    def pick(name: str, key: str, default: str) -> Any:
        if name in env:
            return env[name]
        return own[key] if own.get(key) is not None else default
    ttl = number_of(own.get("ttl_s"))
    return {
        "relay_url": pick("CLAUDE_BRIDGE_URL", "relay_url", "http://127.0.0.1:8765"),
        "channel": pick("FABRIC_CONTROL_CHANNEL", "channel", "fabric:control"),
        # Session state rides its own channel (ADR-029 rule 16), named to end
        # in :control like the control channel, so no inbox ever drains it.
        "state_channel": pick("FABRIC_STATE_CHANNEL", "state_channel", "fabric:state:control"),
        "ttl_s": (int(ttl) if ttl.is_integer() else ttl) if ttl > 0 and ttl != math.inf else (math.inf if ttl > 0 else 30),
    }


def new_id() -> str:
    return gzmsg.mint_id()


def _registry(registry: str | None) -> Any:
    path = roots.hosts_registry(engine=FABRIC_ROOT, empty_is_set=True) if registry is None else registry
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return js.json_parse(fh.read())
    except (OSError, ValueError):
        return None


def operator_addresses(registry: str | None = None) -> set[str]:
    d = _registry(registry)
    hosts = d.get("hosts") if isinstance(d, dict) else None
    if not isinstance(hosts, dict):
        return set()
    return {f"{h}/{js.string(v.get('operator')) if isinstance(v, dict) and v.get('operator') is not None else 'user'}" for h, v in hosts.items()}


def account_addresses(registry: str | None = None) -> set[str]:
    d = _registry(registry)
    placement = d.get("placement") if isinstance(d, dict) else None
    if not isinstance(placement, dict):
        return set()
    return {f"{js.string(host)}/{login}" for login, host in placement.items()}
