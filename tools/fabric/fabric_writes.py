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

The record is `fabric-written.json`, beside a `.lock`, in the account's
own state directory, `identity.agent_state_dir()`, and it is replaced only by
`identity.atomic_write` (agent-fabric ADR-003 rule 1); a missing or unreadable
record reads as empty, which costs at most one extra backup.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sys

_RUNTIME = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "runtime")
if _RUNTIME not in sys.path:
    sys.path.insert(0, _RUNTIME)
import identity  # noqa: E402

MARKER = b"agent-fabric"
SUFFIX = ".before-agent-fabric"
RECORD = "fabric-written.json"  # and its .lock beside it


def state_dir() -> str:
    """The account's state directory, as identity resolves it: a copy of the
    resolution here drifted from it once already (ADR-003 rule 1)."""
    return identity.agent_state_dir()


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
    """Remember that the fabric wrote `content` at `dest`, or found it there
    already: a file that was current when this record began is the fabric's
    too, or its first change upstream would be kept as a person's (review of
    #86). A record that cannot be written costs at most one extra backup
    later, never a lost file, so a failure here is not the caller's failure.

    Bootstrap runs the installer as a child, and two sessions of one
    account can bootstrap at once: the read-modify-replace is under an
    exclusive lock, or the slower writer's replace drops the other's
    entries. An entry already holding this hash writes nothing."""
    path = _record_path()
    key, sha = os.path.abspath(dest), _sha(content)
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        # A lock file only, never written or read: O_CREAT without O_TRUNC,
        # 0600 whatever the umask (ADR-003 §2, A 2026-10-31).
        lock = os.open(path + ".lock", os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC, 0o600)
        try:
            os.fchmod(lock, 0o600)  # one an older build made 0644
            fcntl.flock(lock, fcntl.LOCK_EX)
            doc = _load()
            if doc.get(key) == sha:
                return
            doc[key] = sha
            identity.atomic_write(path, json.dumps(doc, indent=1, sort_keys=True) + "\n", 0o600)
        finally:
            os.close(lock)
    except OSError:
        pass


def written(dest: str) -> bool:
    """`dest` holds exactly what the fabric last wrote there."""
    try:
        with open(dest, "rb") as f:
            return _load().get(os.path.abspath(dest)) == _sha(f.read())
    except OSError:
        return False


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
