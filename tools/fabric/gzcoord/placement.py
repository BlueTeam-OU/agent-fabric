"""tools/fabric/gzcoord/placement.py — whether a TO names an account some
host places, asked of the hosts registry on this disk and of nothing else.

Why it is here and not only in the presence check: a message TO an address
no session will ever read sat in the relay for three days (2026-10-21,
TO: <host>/fabric-coordinator — a role, not a login). The presence check
already answered "not-placed" for it, but it runs only with a token, only
for a real send, and only if the presence process answers; and its
"not sent — --force sends it anyway" line invited the --force that posted
it. The test needs no relay, so it runs before the presence ask and apart
from it: send and compose both call it.

CONTRACT:
  placed_addresses()  the set control/presence.py checks against — each
                      placement entry as <host>/<login>, each host's
                      operator as <host>/<operator or "user"> (agentd.py
                      account_addresses and operator_addresses). A registry
                      that cannot be read, or has no placement table, is
                      Unreadable: unknown is never "nobody is placed".
  judge(to, placed, roles)
                      None for a placed address; {"kind": "role"} when no
                      host places it and its login part is a role slug of
                      the catalogue (a refusal --force does not lift);
                      {"kind": "not-placed"} for any other address no host
                      places (an account being placed right now exists, so
                      send lets --force through).

A placed login that happens to equal a role slug is a login: the placement
is looked at first.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import paths
from . import jsvalues as js
from control import js as js_parse
from .gzmsg import js_trim


class Unreadable(Exception):
    """The registry gave no answer; the message says why, never what it held."""


def registry_path() -> str:
    # agentd.py reads it with the engine root and empty-is-set: the same file.
    return paths.roots.hosts_registry(engine=paths.fabric_root(), empty_is_set=True)


def _read(path: str) -> Any:
    """The registry as the daemon reads it, by the daemon's own parser (control/js.py): NaN, Infinity, a number past 2**53
    rounded as JavaScript does, and a nesting too deep to read refused as ValueError. A registry the daemon takes for
    unreadable, or names another login in, must not be read here as naming an operator or a placed account."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return js_parse.json_parse(fh.read())


def placed_addresses(path: str | None = None) -> set[str]:
    path = registry_path() if path is None else path
    try:
        doc = _read(path)
    except (OSError, ValueError) as e:
        raise Unreadable(f"the hosts registry could not be read ({e.__class__.__name__})") from None
    placement = doc.get("placement") if isinstance(doc, dict) else None
    hosts = doc.get("hosts") if isinstance(doc, dict) else None
    if not isinstance(placement, dict) or not isinstance(hosts, dict):
        raise Unreadable("the hosts registry has no placement and hosts tables")
    out = {f"{js.string(host)}/{login}" for login, host in placement.items()}
    for host, entry in hosts.items():
        operator = entry.get("operator") if isinstance(entry, dict) else None
        out.add(f"{host}/{js.string(operator) if operator is not None else 'user'}")
    return out


def is_operator(address: str, path: str | None = None) -> bool:
    """Whether an address is a host's operator, the only login fabric-ctl's carrier ops answer (ctl.py). A registry that
    cannot be read is False, not Unreadable: the caller then tells the reader what any login can do, and nothing it cannot."""
    try:
        doc = _read(registry_path() if path is None else path)
    except (OSError, ValueError):
        return False
    hosts = doc.get("hosts") if isinstance(doc, dict) else None
    if not isinstance(hosts, dict):
        return False
    named = []      # the scan finishes before it answers: a null entry LATER in the table voids every operator
    for host, entry in hosts.items():
        if entry is None:
            # agentd.operator_list: a null host entry throws in the daemon's own read, so it answers no operator at all,
            # and fabric-ctl then refuses every login. The same registry must not promise a command that is refused.
            return False
        operator = entry.get("operator") if isinstance(entry, dict) else None
        named.append(f"{host}/{js.string(operator) if operator is not None else 'user'}")
    return address in named


def judge(to: str, placed: Iterable[str], roles: Iterable[str]) -> dict[str, Any] | None:
    address = js_trim(to)
    if address in placed:
        return None
    login = address.rsplit("/", 1)[-1]
    if login in roles:
        return {"kind": "role", "address": address, "slug": login}
    return {"kind": "not-placed", "address": address}


def addressee_problem(metadata: dict, roles: Iterable[str]) -> dict[str, Any] | None:
    """What is wrong with the TO of a message, or None. A BROADCAST, a
    TO-ROLE and a message with no TO are not an address to place. Raises
    Unreadable, which the caller says and does not act on."""
    to = metadata.get("TO")
    if metadata.get("BROADCAST") or not to:
        return None
    return judge(to, placed_addresses(), roles)
