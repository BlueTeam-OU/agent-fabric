"""tools/fabric/memory_horizons.py — the review horizons of a drain (agent-fabric ADR-050 rule 8): sections to look at, listed,
never expired. Nothing here deletes, archived or demotes a section; the drain report lists them and a holder confirms
(re-dates), corrects or retires each.

CONTRACT
  load_state(path, stamp)                        -> (state, status)
      the drain's own memory of when each section was last returned by a memory_read: `memory-drain-reads.json`, in the
      draining login's agent state directory. One state for the login, in scopes, because a drain is of one project and
      the login drains several:
        {"fabric": SCOPE, "projects": {project: SCOPE}}      SCOPE = {"seen": {key: day}, "reads": {key: day}}
      the fabric's own corpus (`f:` ids, keys "memory/...") is one scope whichever project drains; a project's corpus
      (`p:` ids, keys ".agent-fabric/memory/...", which every project spells alike) is the scope of that project alone.
      `seen` is the first drain that saw the section. status "new" (no file), "ok", or "unreadable" (a file that is no
      state: it starts over and says so, so the unread list stays empty until the sections have been watched again)
  observe(state, project, rows, stamp)           every section of the rows is `seen` from `stamp` on, if it was not already
  record_reads(state, project, ids_read, corpora, stamp, key_of)
      every section an id of `ids_read` names (`f:<path>#<n>`, `p:<path>#<n>`, n counted from 1 in the slice's file order)
      is last-read `stamp`. The day is the drain's, not the read's: the harvest carries counts, not times. An id names the
      position the section had in the reader's checkout; one moved since is credited to the heading now at that position, so
      a move can credit a neighbour and leave the section actually read unread: a limit of ids that carry positions
  horizons(rows, state, project, stamp)          -> {"aged", "unread", "unread_from"}
      aged     every `solution` section whose *Observed* date is older than 30 days, every `workflow` section older than 90,
               at `stamp` — a confirmation re-dates the tail, so a confirmed section leaves the list on its own
      unread   every section with no read in the last 56 days (8 weeks) that the state has watched for 56 days (`seen`):
               before that the answer is unknown, not "unread" — a section written yesterday was not watched. `unread_from`
               is the first day a section not yet watched long enough can be listed, or None
  save_reads(path, state, live)                  written on every drain, atomically, mode 0600 (mkstemp's), with the keys of
                                                 sections that no longer exist dropped from the scopes this drain read; a
                                                 failure to write is the caller's to report and never turns into a listing.
                                                 Two drains of one login at once lose one's reads (read, then replace)
  keys are the drain report's own: "<slice as the report names it>#<heading>" (the keys of `section_writers`)"""
from __future__ import annotations

import datetime
import json
import os
import re
import tempfile
from collections.abc import Callable
from typing import Any

import memory_check

STATE_FILE = "memory-drain-reads.json"
HORIZON_DAYS = {"solution": 30, "workflow": 90}
UNREAD_DAYS = 56
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def day(text: Any) -> datetime.date | None:
    if not isinstance(text, str) or not DATE_RE.fullmatch(text):
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def _scope(raw: Any) -> dict[str, dict[str, str]] | None:
    """A scope read from the file, or None when it is not one; a key whose date is no date is dropped."""
    if not (isinstance(raw, dict) and isinstance(raw.get("seen"), dict) and isinstance(raw.get("reads"), dict)):
        return None
    return {name: {k: v for k, v in raw[name].items() if isinstance(k, str) and day(v)} for name in ("seen", "reads")}


def _empty() -> dict[str, Any]:
    return {"fabric": {"seen": {}, "reads": {}}, "projects": {}}


def load_state(path: str, stamp: str) -> tuple[dict[str, Any], str]:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return _empty(), "new"
    except (OSError, ValueError):
        return _empty(), "unreadable"
    fabric = _scope(doc.get("fabric")) if isinstance(doc, dict) else None
    projects = doc.get("projects") if isinstance(doc, dict) else None
    if fabric is None or not isinstance(projects, dict):
        return _empty(), "unreadable"
    scopes = {p: _scope(s) for p, s in projects.items() if isinstance(p, str)}
    if any(s is None for s in scopes.values()):
        return _empty(), "unreadable"
    return {"fabric": fabric, "projects": scopes}, "ok"


def scope_of(state: dict[str, Any], prefix: str, project: str) -> dict[str, dict[str, str]]:
    if prefix == "f":
        return state["fabric"]
    return state["projects"].setdefault(project, {"seen": {}, "reads": {}})


def observe(state: dict[str, Any], project: str, rows: list[dict[str, Any]], stamp: str) -> None:
    for r in rows:
        scope_of(state, r["scope"], project)["seen"].setdefault(r["key"], stamp)


def record_reads(state: dict[str, Any], project: str, ids_read: dict[str, Any], corpora: dict[str, str], stamp: str,
                 key_of: dict[str, Callable[[str], str]]) -> dict[str, Any]:
    """`corpora` maps `f` and `p` to a corpus root; `key_of[prefix](rel)` names a slice (its path from the corpus root) the way
    the drain report does."""
    for ident in sorted(ids_read):
        target = memory_check.resolve_section_id(ident, corpora)
        if target is None:
            continue
        prefix, rel, heading = target
        reads = scope_of(state, prefix, project)["reads"]
        key = f"{key_of[prefix](rel)}#{heading}"
        if (day(reads.get(key)) or datetime.date.min) <= day(stamp):
            reads[key] = stamp
    return state


def rows_of(corpora: dict[str, str], key_of: dict[str, Callable[[str], str]]) -> list[dict[str, Any]]:
    """Every section of the corpora as {scope, key, class, observed}, in corpus order. A slice that cannot be read is not a
    row: the staleness check says so; a horizon is no place to."""
    rows = []
    for prefix, root in corpora.items():
        if not os.path.isdir(root):
            continue
        for sl in memory_check.read_corpus(root):
            if "why" in sl:
                continue
            klass = sl["meta"].get("class")
            for heading, text in sl["sections"].items():
                observed, _role = memory_check.observed_of(text)
                rows.append({"scope": prefix, "key": f"{key_of[prefix](sl['rel'])}#{heading}", "class": klass, "observed": observed})
    return rows


def horizons(rows: list[dict[str, Any]], state: dict[str, Any], project: str, stamp: str) -> dict[str, Any]:
    today = day(stamp)
    if today is None:
        raise ValueError(f"stamp {stamp!r} is no YYYY-MM-DD date")
    aged, unread, unwatched = [], [], []
    for r in rows:
        limit = HORIZON_DAYS.get(r["class"])
        seen = day(r["observed"])
        if limit and seen and (today - seen).days > limit:
            aged.append({"key": r["key"], "class": r["class"], "observed": r["observed"], "days": (today - seen).days,
                         "horizon_days": limit})
        scope = scope_of(state, r["scope"], project)
        first = day(scope["seen"].get(r["key"])) or today
        if (today - first).days < UNREAD_DAYS:
            unwatched.append(first + datetime.timedelta(days=UNREAD_DAYS))
            continue
        last = day(scope["reads"].get(r["key"]))
        if last is None or (today - last).days > UNREAD_DAYS:
            unread.append({"key": r["key"], "last_read": scope["reads"].get(r["key"])})
    return {"aged": aged, "unread": unread, "unread_from": min(unwatched).isoformat() if unwatched else None}


def save_reads(path: str, state: dict[str, Any], project: str, live: dict[str, set[str]]) -> None:
    """Writes the state with the keys of sections that no longer exist dropped from the scopes this drain read (`live` maps
    `f` and `p` to the keys it saw). Raises OSError: the caller says so."""
    def pruned(scope: dict[str, dict[str, str]], keys: set[str]) -> dict[str, dict[str, str]]:
        return {name: {k: v for k, v in sorted(scope[name].items()) if k in keys} for name in ("seen", "reads")}
    doc = {"fabric": pruned(state["fabric"], live["f"]),
           "projects": {p: (pruned(s, live["p"]) if p == project else s) for p, s in sorted(state["projects"].items())}}
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=STATE_FILE + ".", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
