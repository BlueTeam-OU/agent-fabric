#!/usr/bin/env python3
"""tools/fabric/persona.py — how people name an agent (agent-fabric ADR-056).

    fabric-persona <login|agent-id>    AI <First> <Surname>, <Role title>
    fabric-persona --json <who>        {login, agent_id, display, first_name, surname, pronoun, role, role_title}
    fabric-persona --all [--json]      one line (or one JSON list) for every agent

People use the name, surname and role, never the login slug (the owner,
2026-10-13). The login <-> id pair is identities/keys/lineage.json, the
first name and surname identities/personas/claims.json, the role is read
off the login, its title off identities/roles/catalog.json. An agent that
has no claim yet is unknown here: a half-built name would be quoted.

Exit 0 answered, 2 unknown agent (one line on stderr).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roots  # noqa: E402


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def role_of(login: str, role_ids: list[str], coordinator_logins: set[str], root: str | None = None) -> str | None:
    """The role a login holds: a coordinator holder, else a catalog role's id alone, with `-<n>`, or with a
    locale suffix that exists under identities/roles/<role>/locale/. Longest id first: `a-b` before `a`."""
    if login in coordinator_logins:
        return "fabric-coordinator"
    for role in sorted(role_ids, key=len, reverse=True):
        if login == role:
            return role
        if not login.startswith(role + "-"):
            continue
        rest = login[len(role) + 1:]
        if re.fullmatch(r"\d+", rest) or os.path.isdir(roots.locale_dir(role, rest, root=root)):
            return role
    return None


def agents(root: str | None = None) -> list[dict]:
    lineage = _load(os.path.join(roots.keys_dir(root=root), "lineage.json"))
    claims = _load(roots.personas("claims.json", root=root)).get("claims") or {}
    catalog = {r["id"]: r.get("short_title") or r.get("title") or r["id"] for r in _load(roots.role_catalog(root=root)).get("roles") or []}
    authority = _load(roots.policy("authority.json", root=root))
    definitions = authority.get("role_definitions") or {}
    holders: set[str] = set()
    for d in [definitions] if isinstance(definitions, dict) else definitions:
        if d.get("role") == "fabric-coordinator":
            holders |= set(d.get("holders") or [])
    out = []
    for aid, rec in lineage.items():
        claim = claims.get(aid)
        login = rec.get("login")
        if not isinstance(claim, dict) or not login:
            continue
        role = role_of(login, list(catalog), holders, root)
        title = catalog.get(role, role) if role else None
        first, surname = claim["first_name"], claim["surname"]
        out.append({
            "login": login, "agent_id": aid, "display": f"AI {first} {surname}, {title}" if title else f"AI {first} {surname}",
            "first_name": first, "surname": surname, "pronoun": claim.get("pronoun"), "role": role, "role_title": title,
        })
    return out


def find(who: str, root: str | None = None) -> dict | None:
    for a in agents(root):
        if who in (a["login"], a["agent_id"]):
            return a
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-persona", description="Name an agent as AI <First> <Surname>, <Role title>.")
    ap.add_argument("who", nargs="?", help="a login or an agent id")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--all", action="store_true", help="every agent")
    args = ap.parse_args(argv)
    if args.all == bool(args.who):
        ap.error("give a login or an agent id, or --all")
    if args.all:
        found = agents()
        if args.json:
            print(json.dumps(found, indent=2, ensure_ascii=False))
        else:
            for a in found:
                print(a["display"])
        return 0
    a = find(args.who)
    if a is None:
        print(f"fabric-persona: no agent {args.who!r} with a name claim", file=sys.stderr)
        return 2
    print(json.dumps(a, indent=2, ensure_ascii=False) if args.json else a["display"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
