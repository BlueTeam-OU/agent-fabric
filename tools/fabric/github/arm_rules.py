"""tools/fabric/github/arm_rules.py — the project's rules for arm and the
gates that are plain reads of the PR body or of arm.json: the two exception
classes the arm gates raise, the owner's-word phrase, the AWAITING-SUPPLY
and Class: lines, and the arm.json loader. Split out of arm.py, unchanged;
the contract and the order of the gates are that module's header."""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from github import common  # noqa: E402


class Refused(Exception):
    """Gate refusal: exit 1."""


class Unanswered(Exception):
    """A question nobody could answer, or usage: exit 2."""


def has_owner_word(basis: str) -> bool:
    # A fixed phrase, not any sentence with "owner" in it ("the owner has
    # not been asked yet" is not consent — a managed project's PR #894 review): straight
    # or curly apostrophe.
    return re.search(r"owner('|’)s word", basis, re.I) is not None


def head_lines(lines: list[str], n: int = 3) -> str:
    """The first n, as `head -3 | tr '\\n' ' '` wrote them."""
    return "".join(f"{l} " for l in lines[:n])


def config_path() -> str:
    return common.project_config_path("AGENT_FABRIC_ARM_CONFIG", "arm.json")


def load_config(path: str) -> tuple[re.Pattern, re.Pattern | None, dict[str, re.Pattern], str | None]:
    if not path:
        raise Unanswered("no project found for this working copy, so no arm.json to read the security boundary from"
                         " (projects/<id>/integration/gh/arm.json in agent-fabric, or AGENT_FABRIC_ARM_CONFIG)")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        b = doc["boundary"]
        paths = re.compile(b["paths"], re.I)
        exempt = re.compile(b["exempt"]) if b.get("exempt") else None
        classes = {str(k).lower(): re.compile(v) for k, v in (doc.get("classes") or {}).items()}
        waiver_role = doc.get("waiver_role")
        if waiver_role is not None and not (isinstance(waiver_role, str) and waiver_role.strip()):
            raise TypeError("waiver_role is not a role's slug")
        # The project's own statement of what must stay boundary: a case the
        # patterns no longer match is a boundary narrowed by mistake, and
        # arming on it would judge with rules the project did not mean
        # (lint holds the same, and that no case is dropped unretired).
        missed = [c for c in (b.get("cases") or []) if (exempt and exempt.search(c)) or not paths.search(c)]
    except FileNotFoundError:
        raise Unanswered(f"this project declares no arm.json ({path}); the security boundary cannot be judged") from None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, re.error) as e:
        raise Unanswered(f"{path} is not a usable arm.json ({type(e).__name__}: {e})") from None
    if missed:
        raise Unanswered(f"{path}: boundary case(s) not boundary under its own patterns — {', '.join(missed[:3])}"
                         " — the security boundary cannot be judged")
    return paths, exempt, classes, waiver_role


def unmet_supply(body: str) -> list[str]:
    """Each AWAITING-SUPPLY login with no `<sha>..<sha>: <login>` range
    line in the body — the reading fabric-pr owed-supply makes."""
    out = []
    for line in body.split("\n"):
        m = re.match(r"^\s*-?\s*AWAITING-SUPPLY:\s*(\S+)", line)
        if not m:
            continue
        who = m.group(1).split("/")[-1]
        if not re.search(r"[0-9a-f]{7,40}\.\.[0-9a-f]{7,40}:\s*" + re.escape(who) + r"([^A-Za-z0-9_-]|$)", body):
            out.append(who)
    return out


def stated_class(body: str, classes: dict[str, re.Pattern]) -> str:
    if not classes:
        return ""
    names = "|".join(re.escape(c) for c in sorted(classes, key=len, reverse=True))
    for line in body.split("\n"):
        m = re.match(r"^[\s*_-]*Class:[\s*_]*(" + names + ")", line, re.I)
        if m:
            return m.group(1).lower()
    return ""
