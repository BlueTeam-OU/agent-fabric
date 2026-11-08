"""tools/fabric/lint_rules/mechanisms.py — agent-fabric ADR-067 rules 2 and 3 over the tracked tree: policies/mechanisms.json
names each cross-cutting mechanism's owning module and status, and a claim it makes that the tree does not bear out is a
finding. An `enforced` entry is held to what a guard is: its checker and exceptions file tracked, the checker loaded by a
lint rule and by the pre-commit hook. A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import json
import os
import re

from .base import _tracked

POLICY = "policies/mechanisms.json"
STATUSES = ("enforced", "pending", "planned")
JOB = re.compile(r"[a-z][a-z0-9-]*/j[0-9]+")
ADR = re.compile(r"ADR-[0-9]{3}")
LINT_RULES = "tools/fabric/lint_rules"
PRE_COMMIT = "tools/fabric/guards/commit_hooks.py"


def _loads(root: str, rel: str, stem: str) -> bool:
    # How lint and the hook take in a checker today: `_load("state_writes")` by path, or a plain import. A checker named
    # only in a comment is not loaded, and the word boundary keeps `state_writes2` from passing for `state_writes`.
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    return re.search(rf"""(?:_load\(["']{re.escape(stem)}["']\)|^\s*import {re.escape(stem)}\b|^\s*from {re.escape(stem)} import)""",
                     text, re.M) is not None


def mechanism_findings(root: str) -> list[str]:
    try:
        with open(os.path.join(root, POLICY), encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return []           # instance data (ADR-045 rule 3): a stripped engine copy has no catalogue to judge
    except (OSError, ValueError) as exc:
        return [f"{POLICY}: cannot be read as JSON ({exc.__class__.__name__}); ADR-067 is not judged"]
    entries = doc.get("mechanisms") if isinstance(doc, dict) else None
    if not isinstance(entries, dict) or not entries:
        return [f"{POLICY}: needs a non-empty \"mechanisms\" object (ADR-067 rule 2)"]
    tracked = set(_tracked(root))
    rules = [r for r in tracked if r.startswith(LINT_RULES + "/") and r.endswith(".py")]
    out: list[str] = []
    for name, e in sorted(entries.items()):
        where = f"{POLICY}: {name}"
        if not isinstance(e, dict):
            out.append(f"{where}: an entry is an object")
            continue
        if not ADR.fullmatch(str(e.get("adr") or "")):
            out.append(f"{where}: \"adr\" names the record it comes from, ADR-NNN")
        owner = e.get("owner")
        if not isinstance(owner, str) or owner not in tracked:
            out.append(f"{where}: owner {owner!r} is not a tracked file")
        status = e.get("status")
        if status not in STATUSES:
            out.append(f"{where}: status {status!r} is not one of {', '.join(STATUSES)}")
            continue
        for key in ("checker", "exceptions"):
            path = e.get(key)
            if status == "enforced" and not path:
                out.append(f"{where}: an enforced mechanism names its {key} (ADR-067 rule 2)")
            elif status == "enforced" and path not in tracked:
                out.append(f"{where}: {key} {path!r} is not a tracked file")
        if status == "enforced" and isinstance(e.get("checker"), str) and e["checker"] in tracked:
            stem = os.path.splitext(os.path.basename(e["checker"]))[0]
            if not any(_loads(root, r, stem) for r in rules):
                out.append(f"{where}: enforced, but no lint rule under {LINT_RULES}/ loads {e['checker']}")
            if not _loads(root, PRE_COMMIT, stem):
                out.append(f"{where}: enforced, but the pre-commit hook ({PRE_COMMIT}) does not load {e['checker']}")
        if status == "pending" and not JOB.fullmatch(str(e.get("job") or "")):
            out.append(f"{where}: a pending mechanism names the job building its checker as <login>/j<n>")
        if status == "planned" and not str(e.get("waits_on") or "").strip():
            out.append(f"{where}: a planned mechanism says what it waits on (\"waits_on\")")
    return out
