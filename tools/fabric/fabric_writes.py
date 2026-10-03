#!/usr/bin/env python3
"""tools/fabric/fabric_writes.py — what the fabric last wrote over a file a
person may also edit, so a later write keeps the person's version and never
the fabric's own.

bootstrap.py and install_agent_files.py replace files in an account's home
and workspace (CLAUDE.md, the agent files, the guards, the skills, the
units). A file the fabric did not write is kept beside it before it is
replaced. Two earlier rules each lost something:

- the marker alone ("agent-fabric" in the file) re-made the backup every
  time a fabric file without the marker changed, so the second change
  replaced the person's original with the fabric's own previous file;
- backing up only once then lost a person's LATER edit: once the backup
  existed, their second version was replaced with no copy and no line
  (review of #86).

So the fabric records the hash of every file it writes. A file is the
fabric's own when it carries the marker or its content is what the fabric
last wrote there; otherwise it is a person's, and it is kept under the first
free name of `<dest>.before-agent-fabric`, `.1`, `.2` …, with its mode, never
over another backup, and not again if a backup already holds that content.

The record is `fabric-written.json` in the account's own state directory
(runtime/identity.py's rule: AGENT_FABRIC_STATE_DIR, else
$XDG_STATE_HOME/agent-fabric, then agents/<login>); a missing or unreadable
record reads as empty, which costs at most one extra backup.
"""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import shutil
import tempfile

MARKER = b"agent-fabric"
SUFFIX = ".before-agent-fabric"
RECORD = "fabric-written.json"


def state_dir() -> str:
    """runtime/identity.py's agent_state_dir(), without importing it:
    tests/test_fabric_writes.py holds the two equal."""
    override = os.environ.get("AGENT_FABRIC_STATE_DIR")
    root = os.path.abspath(override) if override else os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"),
        "agent-fabric")
    return os.path.join(root, "agents", pwd.getpwuid(os.geteuid()).pw_name)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path() -> str:
    return os.path.join(state_dir(), RECORD)


def _load() -> dict[str, str]:
    try:
        with open(_record_path(), encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def record(dest: str, content: bytes) -> None:
    """Remember that the fabric wrote `content` at `dest`. A record that
    cannot be written costs at most one extra backup later, never a lost
    file, so a failure here is not the caller's failure."""
    path = _record_path()
    doc = _load()
    doc[os.path.abspath(dest)] = _sha(content)
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".fabric-written-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except OSError:
        pass


def _backups(dest: str) -> list[str]:
    base = dest + SUFFIX
    found = [base] if os.path.lexists(base) else []
    d, name = os.path.split(base)
    try:
        names = os.listdir(d or ".")
    except OSError:
        names = []
    numbered = []
    for n in names:
        if n.startswith(name + ".") and n[len(name) + 1:].isdigit():
            numbered.append((int(n[len(name) + 1:]), os.path.join(d, n)))
    return found + [p for _, p in sorted(numbered)]


def keep_person_version(dest: str) -> str | None:
    """Before `dest` is replaced: if it holds a person's version, copy it
    to the first free backup name, with its mode, and return that name;
    otherwise None. OSError propagates: the caller says it in one line."""
    if not os.path.isfile(dest):
        return None
    with open(dest, "rb") as f:
        data = f.read()
    if MARKER in data or _load().get(os.path.abspath(dest)) == _sha(data):
        return None
    existing = _backups(dest)
    for p in existing:
        try:
            with open(p, "rb") as f:
                if f.read() == data:
                    return None
        except OSError:
            continue
    base = dest + SUFFIX
    target = base if not os.path.lexists(base) else f"{base}.{len(existing)}"
    while os.path.lexists(target):
        target = f"{base}.{int(target.rsplit('.', 1)[1]) + 1}"
    shutil.copy2(dest, target)
    return target
