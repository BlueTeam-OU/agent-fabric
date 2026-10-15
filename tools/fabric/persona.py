#!/usr/bin/env python3
"""tools/fabric/persona.py — how people name an agent (agent-fabric ADR-056).

    fabric-persona <login|agent-id>    AI <First> <Surname>, <Role title>
                                       (AI <Surname>, <Role title> while its first name is not chosen yet)
    fabric-persona --json <who>        {login, agent_id, display, first_name, surname, pronoun, role, role_title}
    fabric-persona --all [--json]      one line (or one JSON list) for every agent

People use the name, surname and role, never the login slug (the owner,
2026-10-13). The login <-> id pair is identities/keys/lineage.json, the
first name and surname identities/personas/claims.json, the role is read
off the login, its title off identities/roles/catalog.json. An agent that
has no claim yet is unknown here: a half-built name would be quoted. A
claim whose first_name is null was made by provisioning (new-agent
--surname, ADR-056 rule 4): the agent is named by its surname until it
chooses its sex and then a first name of that sex (rules 5-6), and
asked by the agent itself, a line on stderr says so, in that order.

Exit 0 answered, 2 unknown agent or a claim that is no name (one line on stderr, naming the agent id; with
--all the good ones are printed and each bad one is reported, exit 2 if any was).
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roots  # noqa: E402


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def role_of(login: str, role_ids: list[str], coordinator_logins: set[str], root: str | None = None) -> str | None:
    """The role a login holds: a coordinator holder, else the longest catalog role id the login is, or starts with
    followed by `-<suffix>`: a number (`python-dev-02`), a locale (`language-culture-ge`) or a jurisdiction
    (`legal-expert-ee-eu`). Longest id first, so `a-b-x` is `a-b`'s when both `a` and `a-b` are roles. A suffix
    need not name a directory: legal-expert-ee-eu has no locale/ee-eu/ and was left roleless when it had to
    (2026-10-15). `root` is kept for callers; the role no longer depends on the tree."""
    if login in coordinator_logins:
        return "fabric-coordinator"
    for role in sorted(role_ids, key=len, reverse=True):
        if login == role or (login.startswith(role + "-") and len(login) > len(role) + 1):
            return role
    return None


def _text(v: object) -> bool:
    return isinstance(v, str) and bool(v.strip())


def agents(root: str | None = None, bad: list[str] | None = None) -> list[dict]:
    """Every agent with a usable claim. A claim that is not an object, or lacks a first name or surname, is left
    out and its agent id appended to `bad` when the caller gives one (a half-built name would be quoted). A first
    name that is null is not chosen yet: the agent is named by its surname alone (ADR-056 rules 4-5)."""
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
        if claim is None or not login:
            continue
        pending = isinstance(claim, dict) and "first_name" in claim and claim["first_name"] is None
        if not (isinstance(claim, dict) and (pending or _text(claim.get("first_name"))) and _text(claim.get("surname"))):
            if bad is not None:
                bad.append(aid)
            continue
        role = role_of(login, list(catalog), holders, root)
        title = catalog.get(role, role) if role else None
        first, surname = claim["first_name"], claim["surname"]
        name = f"AI {surname}" if pending else f"AI {first} {surname}"
        out.append({
            "login": login, "agent_id": aid, "display": f"{name}, {title}" if title else name,
            "first_name": first, "surname": surname, "pronoun": claim.get("pronoun"), "role": role, "role_title": title,
        })
    return out


def find(who: str, root: str | None = None, bad: list[str] | None = None) -> dict | None:
    """The one lookup by login or agent id; a malformed claim is left out and reported in `bad`, as agents() does."""
    for a in agents(root, bad):
        if who in (a["login"], a["agent_id"]):
            return a
    return None


def _culture(surname: str) -> str:
    """The surname entry's `from` (identities/personas/surnames.json); "" when it cannot be read."""
    try:
        listed = _load(roots.personas("surnames.json")).get("surnames") or []
    except (OSError, ValueError, AttributeError):
        return ""
    return next((str(e.get("from") or "") for e in listed if isinstance(e, dict) and e.get("surname") == surname), "")


def _remind(found: list[dict]) -> None:
    """The agent itself, asking with no first name chosen, is told the order (ADR-056 rules 5-6, A 2026-10-15): its
    sex first, then a first name of that sex from the surname's culture. On stderr, so the name on stdout stays one
    line a caller can quote. The sex is the profile's (settings/profile.json), never the claim's."""
    me = pwd.getpwuid(os.getuid()).pw_name
    for a in found:
        if a["login"] == me and a["first_name"] is None:
            culture = _culture(a["surname"]) or f"the culture {a['surname']} comes from"
            print(f"fabric-persona: you have no first name yet: choose your sex first (F or M, for your avatar; ADR-056 "
                  f"§5 rule 6), then a first name of that sex from {culture} (rule 5), and propose the name to "
                  "fabric-coordinator for identities/personas/claims.json", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-persona", description="Name an agent as AI <First> <Surname>, <Role title>.")
    ap.add_argument("who", nargs="?", help="a login or an agent id")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--all", action="store_true", help="every agent")
    args = ap.parse_args(argv)
    if args.all == bool(args.who):
        ap.error("give a login or an agent id, or --all")
    if args.all:
        broken: list[str] = []
        found = agents(bad=broken)
        if args.json:
            print(json.dumps(found, indent=2, ensure_ascii=False))
        else:
            for a in found:
                print(a["display"])
        _remind(found)
        for aid in broken:
            print(f"fabric-persona: the claim of {aid} is not {{surname, first_name}}", file=sys.stderr)
        return 2 if broken else 0
    broken = []
    a = find(args.who, bad=broken)
    if a is None and broken:
        lineage = _load(os.path.join(roots.keys_dir(), "lineage.json"))
        for aid in broken:
            if args.who in (aid, lineage.get(aid, {}).get("login")):
                print(f"fabric-persona: the claim of {aid} is not {{surname, first_name}}", file=sys.stderr)
                return 2
    if a is None:
        print(f"fabric-persona: no agent {args.who!r} with a name claim", file=sys.stderr)
        return 2
    print(json.dumps(a, indent=2, ensure_ascii=False) if args.json else a["display"])
    _remind([a])
    return 0


if __name__ == "__main__":
    sys.exit(main())
