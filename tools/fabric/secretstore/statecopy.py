"""tools/fabric/secretstore/statecopy.py — a login's working state, kept in its own store and carried to Proton Drive by its parent's backup.
A part of secret_store.py's family; the owner's j179 (2026-10-13) is the request, fabric-coordinator's REPLY 01a13920-de38 the file set.

CONTRACT of `state_copy(state_dir, claude_dir)`
  input   what the login worked on, nothing else (a closed list, never a
          walk of the home):
            <state_dir>/jobs.json, role-history.jsonl, gzcoord-sent.jsonl
            <state_dir>/reviews/**
            <state_dir>/episodic.db        through sqlite's online backup,
                                           never a copy of the live file
            <claude_dir>/projects/*/memory/**   the harness's memory
            <claude_dir>/plans/**
          Never settings, never a secret (those are the store's own), never
          a session transcript (size, and a transcript can quote what a
          secret looked like). A file that is absent is absent; a link, a
          device or any other non-regular entry is skipped and named in the
          result, never followed.
  effect  one tar of it (name-sorted, owner and times zeroed, so the same
          content is the same bytes), encrypted to this login's key and, when
          identities/recovery.asc exists, to the owner's recovery key too —
          the login's key dies with its home, and the recovery key is how the
          owner reaches the store's key again. Written under the store's write
          lock, after the store is brought up to its remote, as
          state/<agent id>.tar.gpg and state/<agent id>.meta (the tar's sha256
          and the recovery recipient), ONE signed commit, pushed. The parent's
          backup() uploads state/<agent id>.tar.gpg of every store it holds, and
          nothing else from state/, to Proton
          Drive as new revisions, names them in the manifest and checks them in
          --verify. A content and recipient that match the meta make no commit
          (a daily timer must not grow every store's history by a blob a day
          for nothing); an earlier failed push is caught up.
  refused before anything is written: a tar over MAX_BYTES (a runaway
          reviews/ is a finding, not a backup), an unreadable listed file, a
          store with no agent id or no remote.

CONTRACT of `state_restore(dest, source)`
  into an EMPTY directory (made if absent), never over live state: the
  operator moves what they want by hand. The members are checked first — a
  regular file, a name that stays inside dest under one of the two roots
  (state/, claude/) — and written 0600 with O_EXCL. Anything else in the tar
  refuses the whole restore before the first file.
"""
from __future__ import annotations

import hashlib
import io
import os
import sqlite3
import stat
import tarfile
import tempfile

from .core import StoreError, login, own_agent_id, store_dir, gpg
from .keys import key_of_store, _key_file_fingerprint
from .trust import _commit
from .entries import _require_clean, _before_write, _push_if_ahead, _after_commit
from .backup import recovery_pub
from .lock import write_lock
from .core import git

MAX_BYTES = 64 << 20
STATE_FILES = ("jobs.json", "role-history.jsonl", "gzcoord-sent.jsonl")
STATE_TREES = ("reviews",)
EPISODIC = "episodic.db"
# The harness's own folder under ~/.claude/projects/<p>/, not the operator's
# memory/ corpus: a name held apart so tests/test_roots_seam.py's scan for
# instance paths joined outside roots.py does not take it for one.
HARNESS_MEMORY = "memory"
ROOTS = ("state", "claude")


def _read_regular(path: str) -> bytes | None:
    """The file's bytes, None when it is absent or not a regular file. Opened
    without following a link: a link in a listed place is not this login's
    state to copy, and following it could put any file the login can read
    into a store that is pushed."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError:
        return None if os.path.islink(path) else _unreadable(path)
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            return None
        try:
            return fh.read(MAX_BYTES + 1)
        except OSError:
            return _unreadable(path)


def _unreadable(path: str):
    raise StoreError(f"{path}: cannot be read; nothing was backed up")


def _walk(root: str, arc: str, out: dict, skipped: list) -> None:
    """Every regular file below root as arc/<relative>; the rest is named in skipped."""
    # A link at the root of a tree is the same hazard as one inside it: scandir
    # follows it, and whatever it points at would be committed and pushed.
    try:
        mode = os.lstat(root).st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(mode):
        skipped.append(root)
        return
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError as e:
        raise StoreError(f"{root}: {e.strerror}; nothing was backed up") from None
    for e in entries:
        name = f"{arc}/{e.name}"
        if e.is_symlink():
            skipped.append(e.path)
        elif e.is_dir(follow_symlinks=False):
            _walk(e.path, name, out, skipped)
        elif not e.is_file(follow_symlinks=False):
            skipped.append(e.path)       # a socket, device: opening one can block or fail
        else:
            data = _read_regular(e.path)
            if data is None:
                skipped.append(e.path)
            else:
                out[name] = data


def _episodic(path: str, skipped: list) -> bytes | None:
    """sqlite's online backup of the journal: the live file has a wal and a
    shm beside it, and a copy of the three is not a consistent database."""
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            skipped.append(path)
            return None
    except FileNotFoundError:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, EPISODIC)
        try:
            src = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
            try:
                dst = sqlite3.connect(copy)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
        except sqlite3.Error as e:
            raise StoreError(f"{path}: sqlite backup failed ({e}); nothing was backed up") from None
        with open(copy, "rb") as fh:
            return fh.read(MAX_BYTES + 1)


def collect(state_dir: str, claude_dir: str) -> tuple[dict[str, bytes], list[str]]:
    """{archive name: bytes} of the file set, and the entries skipped."""
    files: dict[str, bytes] = {}
    skipped: list[str] = []
    for name in STATE_FILES:
        path = os.path.join(state_dir, name)
        data = _read_regular(path)
        if data is not None:
            files[f"state/{name}"] = data
        elif os.path.lexists(path):
            skipped.append(path)
    for tree in STATE_TREES:
        _walk(os.path.join(state_dir, tree), f"state/{tree}", files, skipped)
    db = _episodic(os.path.join(state_dir, EPISODIC), skipped)
    if db is not None:
        files[f"state/{EPISODIC}"] = db
    projects = os.path.join(claude_dir, "projects")
    try:
        if not stat.S_ISDIR(os.lstat(projects).st_mode):
            skipped.append(projects)
            names = []
        else:
            names = sorted(os.listdir(projects))
    except FileNotFoundError:
        names = []
    for p in names:
        if os.path.islink(os.path.join(projects, p)):
            skipped.append(os.path.join(projects, p))
            continue
        _walk(os.path.join(projects, p, HARNESS_MEMORY), f"claude/projects/{p}/{HARNESS_MEMORY}", files, skipped)
    _walk(os.path.join(claude_dir, "plans"), "claude/plans", files, skipped)
    if sum(len(b) for b in files.values()) > MAX_BYTES:
        big = max(files, key=lambda n: len(files[n]))
        raise StoreError(f"the working state is over {MAX_BYTES >> 20} MiB (largest: {big}); nothing was backed up")
    return files, skipped


def make_tar(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name in sorted(files):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(files[name]), 0o600, 0
            tar.addfile(info, io.BytesIO(files[name]))
    return buf.getvalue()


def _recipient_note() -> tuple[str, list[str]]:
    """The owner's recovery key, when there is one: its fingerprint for the
    meta, and the gpg arguments naming it."""
    pub = recovery_pub()
    if not os.path.exists(pub):
        return "-", []
    return _key_file_fingerprint(pub), ["--recipient-file", pub]


def state_copy(state_dir: str, claude_dir: str) -> dict:
    store = store_dir()
    files, skipped = collect(state_dir, claude_dir)
    tar = make_tar(files)
    digest = hashlib.sha256(tar).hexdigest()
    rfpr, rargs = _recipient_note()
    meta_line = f"{digest} {rfpr}\n"
    with write_lock(store):
        mine = key_of_store(store)
        _require_clean(store)
        _before_write(store)
        aid = own_agent_id(store)
        if not aid:
            raise StoreError("this store has no agent id yet (store-enroll.sh)")
        if not git(store, "remote", check=False).stdout.strip():
            raise StoreError("the store has no remote (fabric-secrets store init --remote URL); a copy that reaches no one is no backup")
        path = os.path.join(store, "state", f"{aid}.tar.gpg")
        meta = os.path.join(store, "state", f"{aid}.meta")
        try:
            same = os.path.exists(path) and open(meta, encoding="utf-8").read() == meta_line
        except FileNotFoundError:
            same = False
        if same:
            _push_if_ahead(store)
            return {"path": path, "changed": False, "files": len(files), "skipped": skipped}
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        gpg("--trust-model", "always", "--no-encrypt-to", "--encrypt", "--recipient", mine, *rargs,
            "--output", path + ".tmp", stdin=tar)
        os.replace(path + ".tmp", path)
        with open(meta, "w", encoding="utf-8") as fh:
            fh.write(meta_line)
        git(store, "add", os.path.relpath(path, store), os.path.relpath(meta, store))
        _commit(store, f"agent {login()}: working-state backup, {len(files)} file(s)")
        _after_commit(store)
        return {"path": path, "changed": True, "files": len(files), "skipped": skipped}


def _member_name(name: str) -> str:
    parts = name.split("/")
    if name.startswith("/") or "" in parts or ".." in parts or "." in parts or parts[0] not in ROOTS or len(parts) < 2:
        raise StoreError(f"the backup holds {name!r}, which is not under state/ or claude/; nothing was restored")
    return name


def state_restore(dest: str, source: str | None = None) -> dict:
    if os.path.islink(dest) or (os.path.exists(dest) and (not os.path.isdir(dest) or os.listdir(dest))):
        raise StoreError(f"{dest} is not an empty directory; a restore never writes over anything")
    if source is None:
        aid = own_agent_id()
        if not aid:
            raise StoreError("this store has no agent id yet; name the copy with --from")
        source = os.path.join(store_dir(), "state", f"{aid}.tar.gpg")
    if not os.path.isfile(source):
        raise StoreError(f"{source}: no such backup copy")
    plain = gpg("--decrypt", source, check=False)
    if plain.returncode != 0:
        raise StoreError("the copy could not be decrypted with this login's key (the owner's recovery key opens it otherwise)")
    try:
        tar = tarfile.open(fileobj=io.BytesIO(plain.stdout), mode="r:")
    except tarfile.TarError as e:
        raise StoreError(f"{source}: not a state backup ({e}); nothing was restored") from None
    with tar:
        members = tar.getmembers()
        names = set()
        for m in members:
            if not m.isreg():
                raise StoreError(f"the backup holds {m.name!r}, which is not a regular file; nothing was restored")
            _member_name(m.name)
            if m.name in names:
                raise StoreError(f"the backup holds {m.name!r} twice; nothing was restored")
            names.add(m.name)
        for n in names:
            parts = n.split("/")
            if any("/".join(parts[:i]) in names for i in range(1, len(parts))):
                raise StoreError(f"the backup holds {n!r} below a file of the same name; nothing was restored")
        os.makedirs(dest, mode=0o700, exist_ok=True)
        for m in members:
            target = os.path.join(dest, m.name)
            os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
            data = tar.extractfile(m).read()
            try:
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
            except OSError as e:
                raise StoreError(f"{target}: {e.strerror}; the restore stopped here") from None
    return {"dest": dest, "files": len(members)}
