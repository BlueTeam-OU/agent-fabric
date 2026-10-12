"""tools/fabric/control/switch_policy.py — routing/policies/account-switch.json, read and judged
(agent-fabric ADR-052 §5 rule 10).

The account-switch controller (control/account_switch.py) and the corpus lint (tools/fabric/lint.py) both
judge the file here, so what lint lets through is exactly what the controller will run on. Standard library
only, and nothing of the control plane imported: lint loads this by path.

The schema (routing/schemas/account-switch.schema.json) holds the shape; `problems` adds what a schema
cannot say: each land threshold below its eject threshold, an eject threshold at most 1 (at 1 the account is
exhausted, rule 2, and rule 4 moves at once), the pool's accounts distinct template slugs, and a `why` for
every number.
"""
from __future__ import annotations

import json
import re
from typing import Any

NAME = "account-switch.json"
MODES = ("off", "advise", "act")
WINDOWS = ("five_hour", "seven_day")
# The template's name in the coordinator's store, as control/ops/usage.py ACCOUNT_SLUG reads it.
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
# Every number the rules read, by the key its reason is filed under in `why`.
REASONED = ("land", "eject", "perishable", "min_stay_s", "reading_max_age_s", "probe_min_interval_s", "interval_s")


class PolicyError(Exception):
    """The file cannot be run on: the controller moves nothing and says why."""


def _number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def problems(doc: Any) -> list[str]:
    """What is wrong with a parsed policy, in words; [] when the controller can run on it."""
    if not isinstance(doc, dict):
        return ["not a JSON object"]
    out: list[str] = []
    if doc.get("version") != 1:
        out.append("version must be 1")
    if doc.get("mode") not in MODES:
        out.append(f"mode must be one of {', '.join(MODES)}")
    pool = doc.get("pool")
    accounts = pool.get("accounts") if isinstance(pool, dict) else None
    if not (isinstance(pool, dict) and isinstance(pool.get("name"), str) and SLUG.fullmatch(pool["name"])):
        out.append("pool.name must be a lowercase name")
    if not (isinstance(accounts, list) and len(accounts) >= 2):
        out.append("pool.accounts must list at least two template slugs: a pool of one has nowhere to move")
    else:
        bad = [a for a in accounts if not (isinstance(a, str) and SLUG.fullmatch(a))]
        if bad:
            out.append(f"pool.accounts: not a template slug: {', '.join(map(str, bad))}")
        if len(set(map(str, accounts))) != len(accounts):
            out.append("pool.accounts: an account is listed twice")
    for side in ("land", "eject"):
        w = doc.get(side)
        for k in WINDOWS:
            v = w.get(k) if isinstance(w, dict) else None
            if not (_number(v) and 0 < v <= 1):
                out.append(f"{side}.{k} must be a share above 0 and at most 1")
    land, eject = doc.get("land"), doc.get("eject")
    if isinstance(land, dict) and isinstance(eject, dict):
        for k in WINDOWS:
            if _number(land.get(k)) and _number(eject.get(k)) and not land[k] < eject[k]:
                out.append(f"land.{k} must be below eject.{k}: hysteresis needs the gap (rule 5)")
    p = doc.get("perishable")
    p = p if isinstance(p, dict) else {}
    if not (_number(p.get("within_hours")) and 0 < p["within_hours"] <= 168):
        out.append("perishable.within_hours must be above 0 and at most 168 (the seven-day window)")
    if not (_number(p.get("max_utilization")) and 0 <= p["max_utilization"] < 1):
        out.append("perishable.max_utilization must be a share from 0 to below 1")
    if not (_number(p.get("min_interval_s")) and p["min_interval_s"] >= 60):
        out.append("perishable.min_interval_s must be at least 60")
    for k, low in (("min_stay_s", 0), ("reading_max_age_s", 60), ("probe_min_interval_s", 60), ("interval_s", 60)):
        if not (_number(doc.get(k)) and doc[k] >= low):
            out.append(f"{k} must be a number of seconds, at least {low}")
    why = doc.get("why")
    missing = [k for k in REASONED if not (isinstance(why, dict) and isinstance(why.get(k), str) and why[k].strip())]
    if missing:
        out.append(f"why: no reason for {', '.join(missing)} (every number says why it is that number)")
    return out


def load(file: str) -> dict:
    """The committed policy at `file` (roots.routing_policy(NAME)), judged. PolicyError when it is absent,
    not JSON or has a problem."""
    try:
        with open(file, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        raise PolicyError(f"no {NAME} in routing/policies") from None
    except (OSError, ValueError) as e:
        raise PolicyError(f"{NAME}: {type(e).__name__}: {str(e)[:120]}") from None
    bad = problems(doc)
    if bad:
        raise PolicyError(f"{NAME}: " + "; ".join(bad))
    return doc
