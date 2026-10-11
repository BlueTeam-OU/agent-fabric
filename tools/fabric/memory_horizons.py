"""tools/fabric/memory_horizons.py — the review horizons of a drain (agent-fabric ADR-050 rule 8): sections to look at, listed,
never expired. Nothing here deletes, archives or demotes a section; the drain report lists them and a holder confirms
(re-dates), corrects or retires each.

CONTRACT
  reads_state(path, stamp)                       -> (state, status)
      the drain's own memory of when each section was last returned by a memory_read: `memory-drain-reads.json`, in the
      drain's agent state directory. {"since": "YYYY-MM-DD" (the first drain that kept it), "reads": {key: "YYYY-MM-DD"}}.
      status "new" (no file: it starts at `stamp`), "ok", or "unreadable" (a file that is no state: it starts over at
      `stamp` and says so, so the unread list stays empty until it has watched long enough again)
  record_reads(state, ids_read, corpora, stamp)  -> state
      every section an id of `ids_read` names (`f:<path>#<n>`, `p:<path>#<n>`, n counted from 1 in the slice's file order)
      is last-read `stamp`. The day is the drain's, not the read's: the harvest carries counts, not times. An id names the
      position it had in the reader's checkout; a section moved since is credited to the heading now at that position, which
      errs toward "read", never toward a false listing
  horizons(rows, state, stamp)                   -> {"aged", "unread", "unread_from"}
      aged     every `solution` section whose *Observed* date is older than 30 days, every `workflow` section older than 90,
               at `stamp` — a confirmation re-dates the tail, so a confirmed section leaves the list on its own
      unread   every section with no read in the last 56 days (8 weeks), but only once the state has watched for 56 days
               (`since`): before that the answer is unknown, not "unread", and the list is empty with `unread_from` naming
               the day it can begin
  save_reads(path, state)                        written on every drain, atomically, mode 0600 (mkstemp's); a failure to write is the
                                                 caller's to report and never turns into a listing
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


def reads_state(path: str, stamp: str) -> tuple[dict[str, Any], str]:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return {"since": stamp, "reads": {}}, "new"
    except (OSError, ValueError):
        return {"since": stamp, "reads": {}}, "unreadable"
    reads = doc.get("reads") if isinstance(doc, dict) else None
    if not (isinstance(doc, dict) and day(doc.get("since")) and isinstance(reads, dict)):
        return {"since": stamp, "reads": {}}, "unreadable"
    return {"since": doc["since"], "reads": {k: v for k, v in reads.items() if isinstance(k, str) and day(v)}}, "ok"


def record_reads(state: dict[str, Any], ids_read: dict[str, Any], corpora: dict[str, str], stamp: str,
                 key_of: dict[str, Callable[[str], str]]) -> dict[str, Any]:
    """`corpora` maps `f` and `p` to a corpus root; `key_of[prefix]` is the callable that names a slice the way the drain
    report does (corpus root, slice path relative to it) -> the report's slice name."""
    for ident in sorted(ids_read):
        target = memory_check.resolve_section_id(ident, corpora)
        if target is None:
            continue
        prefix, rel, heading = target
        key = f"{key_of[prefix](rel)}#{heading}"
        if (day(state["reads"].get(key)) or datetime.date.min) <= day(stamp):
            state["reads"][key] = stamp
    return state


def rows_of(corpora: dict[str, str], key_of: dict[str, Callable[[str], str]]) -> list[dict[str, Any]]:
    """Every section of the corpora as {key, class, observed}, in corpus order. A slice that cannot be read is not a row:
    the staleness check says so; a horizon is no place to."""
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
                rows.append({"key": f"{key_of[prefix](sl['rel'])}#{heading}", "class": klass, "observed": observed})
    return rows


def horizons(rows: list[dict[str, Any]], state: dict[str, Any], stamp: str) -> dict[str, Any]:
    today = day(stamp)
    if today is None:
        raise ValueError(f"stamp {stamp!r} is no YYYY-MM-DD date")
    aged, unread = [], []
    since = day(state["since"]) or today
    watched = (today - since).days >= UNREAD_DAYS
    for r in rows:
        limit = HORIZON_DAYS.get(r["class"])
        seen = day(r["observed"])
        if limit and seen and (today - seen).days > limit:
            aged.append({"key": r["key"], "class": r["class"], "observed": r["observed"], "days": (today - seen).days,
                         "horizon_days": limit})
        last = day(state["reads"].get(r["key"]))
        if watched and (last is None or (today - last).days > UNREAD_DAYS):
            unread.append({"key": r["key"], "last_read": state["reads"].get(r["key"])})
    return {"aged": aged, "unread": unread,
            "unread_from": None if watched else (since + datetime.timedelta(days=UNREAD_DAYS)).isoformat()}


def save_reads(path: str, state: dict[str, Any], live_keys: set[str]) -> None:
    """Writes the state with the keys of sections that no longer exist dropped. Raises OSError: the caller says so."""
    doc = {"since": state["since"], "reads": {k: v for k, v in sorted(state["reads"].items()) if k in live_keys}}
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
