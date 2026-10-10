"""tools/fabric/memory_use.py — what the fabric-memory server wrote in a login's state, read for a drain (ADR-049).

The server (tools/fabric/memory_mcp/) appends two files to agents/<login>/: memory-marks.jsonl (a session's verdict on
a section: time, id, verdict, note) and memory-calls.jsonl (one line per call: time, tool, hit count, the ids returned,
and for a read whether the last find returned one of them). Agents live on different hosts and the coordinator never
reads another account's state, so the harvest (harvest_memory.py) carries both in the bundle: the marks themselves, and
counts over the calls. Query text is never in either file and never here.

CONTRACT
  read(state_dir, since_ms)  rows whose time is after since_ms (a ms epoch, the store's watermark; 0 reads all):
      marks   [{"t", "id", "verdict", "note"}], file order; a row that is not a mark of the server's shape is dropped
              and counted
      use     {"since_ms", "until_ms", "calls": {tool: n}, "zero_hit_finds", "finds_followed_by_read",
               "ids_read": {id: n}, "marks": n, "unreadable_lines", "notes_withheld"}
      until_ms the latest row time read (>= since_ms): the watermark covers these rows like memories
  A missing file is no rows, not an error; an unreadable one is the same, said in `unreadable_lines`.
  A note that carries a credential by shape (the caller's screen) is withheld, the mark kept."""
from __future__ import annotations

import datetime
import json
import os
import re
from collections.abc import Callable

MARKS, CALLS = "memory-marks.jsonl", "memory-calls.jsonl"
VERDICTS = ("helpful", "wrong", "stale")
NOTE_CLIP = 300
# The ids memory_find returns: f:/p: and a path, then #position for a section. Anything else is not a corpus id.
ID_RE = re.compile(r"^[fp]:[A-Za-z0-9._/-]+(#[0-9]+)?$")


def _ms(stamp: object) -> int | None:
    if not isinstance(stamp, str):
        return None
    try:
        return int(datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def _rows(path: str) -> tuple[list[dict], int]:
    """(the JSON objects of a jsonl file in order, the count of lines that are not one)."""
    rows, bad = [], 0
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return [], 0
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            bad += 1
    return rows, bad


def read(state_dir: str, since_ms: int, credential_hits: Callable[[str], list] = lambda _text: []) -> tuple[list[dict], dict]:
    marks: list[dict] = []
    use: dict = {"since_ms": since_ms, "until_ms": since_ms, "calls": {}, "zero_hit_finds": 0, "finds_followed_by_read": 0,
                 "ids_read": {}, "marks": 0, "unreadable_lines": 0, "notes_withheld": 0}
    until = since_ms
    rows, bad = _rows(os.path.join(state_dir, MARKS))
    use["unreadable_lines"] += bad
    for row in rows:
        at = _ms(row.get("t"))
        ident, verdict, note = row.get("id"), row.get("verdict"), row.get("note", "")
        if at is None or not isinstance(ident, str) or not ID_RE.match(ident) or verdict not in VERDICTS or not isinstance(note, str):
            use["unreadable_lines"] += 1
            continue
        if at <= since_ms:
            continue
        note = " ".join(note.split())[:NOTE_CLIP]
        if note and credential_hits(note):
            note = ""
            use["notes_withheld"] += 1
        marks.append({"t": row["t"], "id": ident, "verdict": verdict, "note": note})
        until = max(until, at)
    use["marks"] = len(marks)
    rows, bad = _rows(os.path.join(state_dir, CALLS))
    use["unreadable_lines"] += bad
    pending = False       # a find not yet followed by a read of one of its ids
    for row in rows:
        at, tool = _ms(row.get("t")), row.get("tool")
        if at is None or not isinstance(tool, str):
            use["unreadable_lines"] += 1
            continue
        if at <= since_ms:
            continue
        until = max(until, at)
        use["calls"][tool] = use["calls"].get(tool, 0) + 1
        ids = [i for i in row.get("ids") or [] if isinstance(i, str) and ID_RE.match(i)] if isinstance(row.get("ids"), list) else []
        if tool == "memory_find":
            use["zero_hit_finds"] += not row.get("hits")
            pending = True
        elif tool == "memory_read":
            for i in ids:
                use["ids_read"][i] = use["ids_read"].get(i, 0) + 1
            if pending and row.get("after_find") is True:
                use["finds_followed_by_read"] += 1
                pending = False
    use["until_ms"] = until
    return marks, use
