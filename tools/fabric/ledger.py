"""tools/fabric/ledger.py — the per-dispatch token ledger, row v1 (review
economics P1): <state>/agents/<login>/ledger.jsonl, one JSON line per
subagent stop (runtime/claude-code/hooks/subagent-ledger.py writes the
Claude rows) and per Codex review run (review_codex.py writes the codex
rows with append()). The row's fields are the hook's docstring and
devex-tooling's INFO 01a139cc; this module owns only the file: where it
is, how a line is appended, and how rows are read back for a reader
(control/ops/usage.py's tokens op).

The path is computed by the hook's rule (AGENT_FABRIC_STATE_DIR, else
XDG_STATE_HOME or ~/.local/state, then agents/<login>), not through
runtime/identity.py, so a writer and the hook land in one file for the
same environment whatever tool resolves it.

Nothing reads the ledger for authorization; it is a measurement.
"""
from __future__ import annotations

import fcntl
import json
import os
import pwd
import re
import time
from datetime import datetime
from typing import Any, Mapping

FILE = "ledger.jsonl"
SCHEMA_VERSION = 1

# The dispatch header: the brief's first fenced block, `agent-fabric-dispatch v1`,
# a JSON object. Each field is copied only in its shape, else unknown — the
# hook's rules (runtime/claude-code/hooks/subagent-ledger.py), because a codex
# row and a claude row for one review must agree on what head_sha means.
HEADER_INFO = "agent-fabric-dispatch v1"
FENCE = re.compile(r"^(`{3,}|~{3,})[ \t]*([^\n`]*?)[ \t]*$", re.MULTILINE)
SHA = re.compile(r"[0-9a-f]{7,64}")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}")
HEADER_IDENT = ("dispatch_id", "parent_session_id", "job_id", "project", "review_id", "purpose")
HEADER_INT = ("pr", "review_round")
HEADER_SHA = ("base_sha", "head_sha")
EVIDENCE = ("pinned", "working-tree")


def state_dir(environ: Mapping[str, str]) -> str:
    login = pwd.getpwuid(os.getuid()).pw_name
    override = environ.get("AGENT_FABRIC_STATE_DIR")
    if override:
        root = os.path.abspath(override)
    else:
        home = environ.get("HOME") or os.path.expanduser("~")
        root = os.path.join(environ.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state"), "agent-fabric")
    return os.path.join(root, "agents", login)


def path(environ: Mapping[str, str]) -> str:
    return os.path.join(state_dir(environ), FILE)


def append(file: str, row: Mapping[str, Any]) -> None:
    """One line, written whole under an exclusive lock: the hook appends to
    the same file from other processes, and a row longer than a pipe buffer
    is not atomic without it. Raises OSError; the caller decides whether a
    measurement that could not be written may stand in a review's way (it
    may not)."""
    line = json.dumps(row, separators=(",", ":"), ensure_ascii=True) + "\n"
    os.makedirs(os.path.dirname(file), mode=0o700, exist_ok=True)
    fd = os.open(file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        # Bounded: a stalled holder (the hook) must not hang a review that has already posted.
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"{file} is locked by another writer") from None
                time.sleep(0.05)
        data = line.encode("ascii")
        while data:   # a short write under the lock is finished before another writer starts
            data = data[os.write(fd, data):]
    finally:
        os.close(fd)


# Past a double's exact integers a count is not a measurement, and equivalent() would overflow on it.
MAX_COUNT = 2 ** 53
LOCK_WAIT_S = 5


def count(v: Any) -> int | None:
    """A token count as a row holds it: a non-negative int below MAX_COUNT, else unknown."""
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < MAX_COUNT else None


def rows(file: str) -> tuple[list[dict], int]:
    """(the rows a reader counts, lines it could not use). Absent file: no
    rows, none skipped; a file that exists and cannot be read raises OSError — no rows
    is a fact about the ledger, not about this read. A line that is not a JSON object of schema_version 1
    is skipped and counted, never guessed at. A Claude subagent stopped
    twice has two rows, the later cumulative: only the last per
    (session_id, agent_id) is kept (the hook's contract). A Claude row with
    either id unknown cannot be paired, so it stays; codex rows are one per
    review run and never paired."""
    try:
        with open(file, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
    except FileNotFoundError:
        return [], 0
    kept: list[dict] = []
    last: dict[tuple, int] = {}
    skipped = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (ValueError, RecursionError):   # a line nested past the parser's stack is a bad line
            skipped += 1
            continue
        if not isinstance(row, dict) or row.get("schema_version") != SCHEMA_VERSION:
            skipped += 1
            continue
        key = (row.get("session_id"), row.get("agent_id"))
        if row.get("engine") == "claude" and all(isinstance(k, str) for k in key):
            if key in last:
                kept[last[key]] = row
                continue
            last[key] = len(kept)
        kept.append(row)
    return kept, skipped


def _zoned(ts: str) -> bool:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def dispatch_header(brief: str) -> tuple[str, dict]:
    """("dispatch", the header's fields in their shapes) when the brief's
    first fenced block is the dispatch header; ("invalid-header", {}) when
    that block's body is not a JSON object; ("inferred", {}) when the brief
    has no header. The header's own `engine` is not copied: a row's engine
    is the one that ran."""
    opening = FENCE.search(brief)
    if not opening or opening.group(2) != HEADER_INFO:
        return "inferred", {}
    fence = opening.group(1)
    close = re.compile(rf"^{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", re.MULTILINE).search(brief, opening.end())
    try:
        doc = json.loads(brief[opening.end():close.start()]) if close else None
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        return "invalid-header", {}
    out: dict = {}
    for k in HEADER_IDENT:
        if isinstance(doc.get(k), str) and IDENT.fullmatch(doc[k]):
            out[k] = doc[k]
    # The header writes the mode as `evidence_mode` (review_brief.dispatch_header); the row's v1 key is `evidence`.
    if doc.get("evidence_mode") in EVIDENCE:
        out["evidence"] = doc["evidence_mode"]
    if isinstance(doc.get("started_at"), str) and len(doc["started_at"]) <= 40 and _zoned(doc["started_at"]):
        out["started_at"] = doc["started_at"]
    for k in HEADER_INT:
        if count(doc.get(k)) is not None:
            out[k] = doc[k]
    for k in HEADER_SHA:
        if isinstance(doc.get(k), str) and SHA.fullmatch(doc[k]):
            out[k] = doc[k]
    if isinstance(doc.get("repository"), str) and REPO.fullmatch(doc["repository"]):
        out["repository"] = doc["repository"]
    return "dispatch", out
