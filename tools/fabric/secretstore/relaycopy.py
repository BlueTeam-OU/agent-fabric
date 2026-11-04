"""tools/fabric/secretstore/relaycopy.py — the relay's database, copied off the host to Proton Drive, and read back.
A part of secret_store.py's family; the owner's request of 2026-10-27 (ADR-034 §7 step 1) is the request.

CONTRACT of `relay_backup(db, state_dir)`
  input   the relay's sqlite database (claude-bridge.db), live. Read through
          sqlite's online backup, never a copy of the file: it runs in WAL
          mode, and the file, its wal and its shm copied one after another
          are not a database. A path that is not a regular file is refused
          (never followed, never created). sqlite's read-only open of a WAL database does leave an empty -wal and
          a 32 KiB -shm beside it when the relay is stopped; the database file itself is not written.
  effect  the snapshot is written to a private temp directory under TMPDIR
          and checked (`PRAGMA integrity_check`) before anything leaves the
          host, hashed (sha256 of the plain snapshot), gzipped, and encrypted
          to this login's key and, when identities/recovery.asc exists, to the
          owner's recovery key (as statecopy.py does: the login's key dies
          with its home). Each stage deletes the one before it, so the peak is
          about two copies, not four. Uploaded to Proton Drive as a NEW
          REVISION of one fixed name, relay/claude-bridge.db.gz.gpg, then a
          manifest {at, sha256, size} as a new revision of
          relay/claude-bridge.manifest.json; the same line is appended to
          <state_dir>/relay-backup.jsonl. The temp directory is removed
          however the run ends (the CLI turns SIGTERM into an exit so the
          timer's stop does too; SIGKILL is the one thing that leaves it).
  refused one line, exit non-zero, nothing left in the temp directory: no
          database, a database that fails its own integrity check, no
          Proton session, a failed upload. The two uploads are not one
          transaction: a run that dies between them leaves a blob the
          manifest does not describe, which `verify` names (the sha differs)
          and the next run replaces.

CONTRACT of `relay_verify()` and `relay_restore(dest)`
  both download the latest revision and the manifest, decrypt with this
  login's key, require a valid signature by the store's own key (backups are
  signed; the encryption key is public, so only the signature says who made
  the revision), gunzip, and require the plain bytes' sha256 to be the
  manifest's and `PRAGMA integrity_check` to say ok. A host that holds only
  the owner's recovery key is refused here (it cannot check the signature):
  the owner opens the blob with `gpg --decrypt` by hand. Not covered: an
  older revision this key really signed, put back with its own manifest.
  `relay_verify` leaves nothing. `relay_restore` writes <dest>/claude-bridge.db
  (0600, O_EXCL) into an EMPTY directory (made if absent) and nothing else;
  it never names, opens or writes the live database, and removes what it
  wrote when any check fails — a restore is a database that passed, or
  nothing.
"""
from __future__ import annotations

import datetime
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import urllib.parse
import zlib

from .core import StoreError, gpg, store_dir
from .backup import PROTON_ROOT, _proton, _proton_folder, _upload, recovery_pub
from .keys import key_of_store

RELAY_FOLDER = f"{PROTON_ROOT}/relay"
BLOB = "claude-bridge.db.gz.gpg"
MANIFEST = "claude-bridge.manifest.json"
LOG = "relay-backup.jsonl"
DB_NAME = "claude-bridge.db"
CHUNK = 1 << 20
# A snapshot of the 754 MB database encrypts in well under this on any disk
# this fleet has; the bound is for a gpg that hangs, not a measured budget.
GPG_TIMEOUT = 1800


def _uri(path: str, query: str) -> str:
    """A sqlite URI for path. Unquoted, a '?', '#' or '%' in the path makes sqlite open a different file
    than the one the regular-file check looked at."""
    return f"file:{urllib.parse.quote(os.path.abspath(path))}?{query}"


def _integrity(path: str) -> None:
    """integrity_check says ok, else a StoreError. immutable=1: the check
    opens a file nobody else writes, and without it sqlite would make a -wal
    and -shm beside a restored copy."""
    try:
        con = sqlite3.connect(_uri(path, "mode=ro&immutable=1"), uri=True)
        try:
            rows = con.execute("PRAGMA integrity_check").fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        raise StoreError(f"the database fails its integrity check ({e})") from None
    if rows != [("ok",)]:
        # sqlite answers one row of many lines ("*** in database main ***", then a line per page): two
        # lines name what failed, and an error stays one line.
        said = " ".join(str(rows[0][0]).splitlines()[:2]) if rows else "no answer"
        raise StoreError(f"the database fails its integrity check ({said})")


def _snapshot(db: str, dest: str) -> None:
    try:
        if not stat.S_ISREG(os.lstat(db).st_mode):
            raise StoreError(f"{db} is not a regular file; nothing was backed up")
    except FileNotFoundError:
        raise StoreError(f"{db}: no such relay database; nothing was backed up") from None
    try:
        src = sqlite3.connect(_uri(db, "mode=ro"), uri=True, timeout=30)
        try:
            out = sqlite3.connect(dest)
            try:
                src.backup(out)
            finally:
                out.close()
        finally:
            src.close()
    except sqlite3.Error as e:
        raise StoreError(f"{db}: sqlite backup failed ({e}); nothing was backed up") from None


def _sha_size(path: str) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def _gzip(src: str, dest: str) -> None:
    with open(src, "rb") as fi, open(dest, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as fo:
        shutil.copyfileobj(fi, fo, CHUNK)


def _recipients() -> list[str]:
    pub = recovery_pub()
    return ["--recipient-file", pub] if os.path.exists(pub) else []


def relay_backup(db: str, state_dir: str) -> dict:
    mine = key_of_store(store_dir())
    with tempfile.TemporaryDirectory(prefix="relay-backup.") as tmp:
        plain = os.path.join(tmp, DB_NAME)
        _snapshot(db, plain)
        _integrity(plain)
        digest, size = _sha_size(plain)
        gz = os.path.join(tmp, "snapshot.gz")
        _gzip(plain, gz)
        os.remove(plain)
        blob_dir = os.path.join(tmp, "up")
        os.mkdir(blob_dir, 0o700)
        blob = os.path.join(blob_dir, BLOB)
        gpg("--trust-model", "always", "--no-encrypt-to", "--sign", "--local-user", mine, "--encrypt", "--recipient", mine, *_recipients(),
            "--output", blob, gz, timeout=GPG_TIMEOUT)
        os.remove(gz)
        line = {"at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sha256": digest, "size": size}
        manifest = os.path.join(blob_dir, MANIFEST)
        with open(manifest, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(line, sort_keys=True) + "\n")
        folder = _proton_folder(RELAY_FOLDER)
        _upload(blob, folder)
        _upload(manifest, folder)
        sent = os.path.getsize(blob)
    try:
        os.makedirs(state_dir, mode=0o700, exist_ok=True)
        with open(os.path.join(state_dir, LOG), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, sort_keys=True) + "\n")
    except OSError as e:
        raise StoreError(f"uploaded, but the manifest line could not be kept ({e.strerror})") from None
    return {**line, "uploaded": sent}


def _fetch(tmp: str, out: str) -> dict:
    """Download the latest revision into tmp, decrypt and gunzip it to `out`;
    return the manifest. Every check but integrity is here: the sha256 of the
    plain bytes against the manifest's."""
    for name in (BLOB, MANIFEST):
        got = _proton("filesystem", "download", "-f", "remove", f"{RELAY_FOLDER}/{name}", tmp, check=False)
        if got.returncode != 0 or not os.path.exists(os.path.join(tmp, name)):
            raise StoreError(f"{RELAY_FOLDER}/{name}: could not be downloaded; no relay backup was read")
    try:
        with open(os.path.join(tmp, MANIFEST), encoding="utf-8") as fh:
            manifest = json.load(fh)
        want = manifest["sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        raise StoreError("the relay backup's manifest is not readable; nothing was restored") from None
    gz = os.path.join(tmp, "snapshot.gz")
    r = gpg("--status-fd", "1", "--decrypt", "--output", gz, os.path.join(tmp, BLOB), check=False, timeout=GPG_TIMEOUT)
    if r.returncode != 0:
        why = (r.stderr.decode(errors="replace").strip().splitlines() or ["no reason given"])[-1]
        raise StoreError(f"the relay backup could not be decrypted with this login's key ({why}); "
                         "the owner's recovery key opens it by hand")
    _require_signed_by_store(r.stdout.decode(errors="replace"))
    h = hashlib.sha256()
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with gzip.open(gz, "rb") as fi, os.fdopen(fd, "wb") as fo:
            for chunk in iter(lambda: fi.read(CHUNK), b""):
                h.update(chunk)
                fo.write(chunk)
    except (OSError, EOFError, zlib.error) as e:
        raise StoreError(f"the relay backup does not decompress ({e})") from None
    finally:
        os.remove(gz)
    if h.hexdigest() != want:
        raise StoreError("the relay backup's sha256 is not the manifest's (a run that stopped between "
                         "its two uploads, or a damaged copy)")
    return manifest


def _require_signed_by_store(status: str) -> None:
    """The encryption key is public: anyone who can write to the Drive folder can encrypt a database to it.
    What only this login can make is its signature, so a revision is accepted only when gpg reports a
    valid one by the store's own key (VALIDSIG's last field is the primary key's fingerprint). A signature
    gpg cannot check at all (no public key) never gets here: gpg exits 2 and _fetch refuses first."""
    mine = key_of_store(store_dir()).upper()
    for line in status.splitlines():
        f = line.split()
        if len(f) > 2 and f[:2] == ["[GNUPG:]", "VALIDSIG"] and f[-1].upper() == mine:
            return
    raise StoreError("the relay backup is not signed by this login's key (a revision put on the Drive by "
                     "someone else, or made before backups were signed); nothing was restored")


def relay_verify() -> dict:
    with tempfile.TemporaryDirectory(prefix="relay-verify.") as tmp:
        out = os.path.join(tmp, DB_NAME)
        manifest = _fetch(tmp, out)
        _integrity(out)
    return manifest


def relay_restore(dest: str) -> dict:
    # Resolved first: 'new/../leaf' does not exist while new is absent, so the emptiness check below would pass
    # a leaf that has files in it.
    dest = os.path.abspath(dest)
    if os.path.islink(dest) or (os.path.exists(dest) and (not os.path.isdir(dest) or os.listdir(dest))):
        raise StoreError(f"{dest} is not an empty directory; a restore never writes over anything")
    # Every directory this run makes, outermost first: a failed restore removes them all, not only the leaf.
    # makedirs gets the resolved path too: handed 'new/../leaf' it also creates new/, which the walk below
    # would not have recorded.
    made, d = [], dest
    while not os.path.exists(d):
        made.insert(0, d)
        d = os.path.dirname(d)
    os.makedirs(dest, mode=0o700, exist_ok=True)
    out = os.path.join(dest, DB_NAME)
    try:
        with tempfile.TemporaryDirectory(prefix="relay-restore.") as tmp:
            manifest = _fetch(tmp, out)
            _integrity(out)
    except BaseException:
        # What this run wrote and nothing else: dest was empty when it began.
        if os.path.lexists(out):
            os.remove(out)
        for d in reversed(made):
            os.rmdir(d)
        raise
    return {**manifest, "dest": dest}
