"""tools/fabric/provisioning/surname.py — `new-agent.sh --surname <Surname>`: provisioning
claims the agent's surname (agent-fabric ADR-056 §5 rule 4, A 2026-10-15); the agent
still chooses its first name in its first session (rule 5), so the claim is written
{surname, first_name: null} — null is "not chosen yet", never a name.

The surname is checked before anything is made, the dry run included: on
identities/personas/surnames.json, and unclaimed in identities/personas/claims.json
(a claim this agent already holds of the same surname is a re-run, not a conflict).
The claim is written once the account has its agent id (lineage.json, store-enroll's,
step 5), into this checkout, and never committed here: fabric-coordinator commits it
with identities/keys/ (the key and the lineage), as it does those."""
from __future__ import annotations

import json
import os

import roots
from provisioning import config as cfg
from provisioning.github_signing_key import Refused, agent_id_of

SURNAMES = "identities/personas/surnames.json"
CLAIMS = "identities/personas/claims.json"


def _path(name: str) -> str:
    return roots.personas(name, engine=cfg.ROOT)


def _load(path: str, shown: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise Refused(f"{shown} cannot be read ({type(exc).__name__}: {exc})") from None
    if not isinstance(doc, dict):
        raise Refused(f"{shown} is not an object")
    return doc


def _agent_id(login: str) -> str | None:
    """The login's agent id when lineage already holds it (a re-run), else None."""
    try:
        return agent_id_of(login, roots.operator_root(engine=cfg.ROOT))
    except Refused:
        return None


def check(login: str, surname: str) -> str | None:
    """Why `surname` cannot be claimed for `login`, or None when it can."""
    listed = {s.get("surname") for s in _load(_path("surnames.json"), SURNAMES).get("surnames") or [] if isinstance(s, dict)}
    if surname not in listed:
        return (f"--surname {surname!r} is not on {SURNAMES} (ADR-056 rule 3: an addition passes its test and is "
                "merged first); nothing made")
    claims = _load(_path("claims.json"), CLAIMS).get("claims") or {}
    mine = _agent_id(login)
    held = {aid: claim.get("surname") if isinstance(claim, dict) else claim for aid, claim in claims.items()}
    if mine in held and held[mine] != surname:
        return f"{login} ({mine}) already claims {held[mine]!r} in {CLAIMS}; a second surname is never claimed; nothing made"
    for aid, name in held.items():
        if name == surname and aid != mine:
            return f"--surname {surname!r} is claimed by {aid} in {CLAIMS}: one agent per surname (ADR-056 rule 4); nothing made"
    return None


def write_claim(login: str, surname: str) -> str:
    """{surname, first_name: null} keyed by the login's agent id into this checkout's claims.json; an existing claim
    of this agent (a re-run, or a first name already chosen) is left as it is. Returns the agent id."""
    aid = agent_id_of(login, roots.operator_root(engine=cfg.ROOT))
    path = _path("claims.json")
    doc = _load(path, CLAIMS)
    claims = doc.get("claims") if isinstance(doc.get("claims"), dict) else {}
    if aid not in claims:
        claims[aid] = {"surname": surname, "first_name": None}
        doc["claims"] = dict(sorted(claims.items()))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.new-agent"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    return aid
