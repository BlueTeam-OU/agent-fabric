"""tools/fabric/signing/proof.py — the timestamp proof of one signature: what
it is keyed by, how it is made, where it waits for its commit (ADR-057 §5
rule 4).

CONTRACT
  key       sha256 of the signature as the commit carries it (armor, with the
            surrounding whitespace of the file git read it from removed),
            hex. A signature is Ed25519, deterministic and bound to the
            payload and the key, so one digest names one signed commit; the
            commit's own id does not exist while git signs.
  proof     an OpenTimestamps file (`ots stamp` of a file holding the key's
            signature), stored whole. Its first digest is the key's input
            hash: matches() compares the two, so a proof copied onto another
            commit (a rewritten commit carries its note along) is told from
            its own.
  spool     <dir>/<key>.ots, 0600 in a 0700 directory, written by rename. It
            is the account's, not the repository's: the commit it belongs to
            is made after fabric-sign returns, in any working copy.
  failure   StampError, with the fact that fixes it. A stamp that did not
            happen is never a proof: the signing fails (ADR-057 §5 rule 2,
            the old wrapper's rule: a signed, unstamped commit is the failure
            that wrapper exists to prevent).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import time

# `ots stamp` files start with this magic, a version byte and the hash
# operation (0x08, sha256) of the stamped file, whose digest follows.
MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
VERSION = b"\x01"
OP_SHA256 = b"\x08"
OTS_DEFAULT = "/usr/local/share/opentimestamps-venv/bin/ots"
# The public calendars answer in about two seconds, and `ots` waits 5 s per
# calendar; a stamp that takes longer than this is a network that is down,
# which is a refusal to sign and not a wait the committer sits through.
STAMP_TIMEOUT_S = 60
# A proof whose commit never came (the object write failed after the
# signature): old enough that no commit is still being made around it.
SPOOL_MAX_AGE_S = 30 * 24 * 3600


class StampError(Exception):
    """The message is the whole answer: what failed and what fixes it."""


def normalize(signature: bytes) -> bytes:
    return signature.strip()


def key_of(signature: bytes) -> str:
    return hashlib.sha256(normalize(signature)).hexdigest()


def proof_digest(proof: bytes) -> str:
    """The sha256 the proof stamps, hex; StampError when the bytes are not a
    proof of a sha256 file."""
    head = len(MAGIC) + len(VERSION) + len(OP_SHA256)
    if len(proof) < head + 32 or not proof.startswith(MAGIC + VERSION + OP_SHA256):
        raise StampError("not an OpenTimestamps proof of a sha256 file")
    return proof[head:head + 32].hex()


def matches(signature: bytes, proof: bytes) -> bool:
    """True only for ONE proof of this signature: git's note carry-over
    concatenates the old note after the new (notes.rewriteMode default), and
    a second proof behind the first is not a proof file."""
    try:
        return proof.find(MAGIC, 1) == -1 and proof_digest(proof) == key_of(signature)
    except StampError:
        return False


def ots_command(env: dict[str, str]) -> str:
    return env.get("FABRIC_SIGN_OTS") or (OTS_DEFAULT if os.access(OTS_DEFAULT, os.X_OK) else "ots")


def stamp(signature: bytes, env: dict[str, str]) -> bytes:
    """The OpenTimestamps proof of `signature`, from the public calendars
    (no Bitcoin client: attestations are not awaited, ADR-057 §7)."""
    ots = ots_command(env)
    with tempfile.TemporaryDirectory(prefix="fabric-sign-") as tmp:
        path = os.path.join(tmp, "signature")
        with open(path, "wb") as f:
            f.write(normalize(signature))
        try:
            # --no-cache: a stamp reads none, and the shared cache's
            # permissions are the old wrapper's trouble, not this path's.
            p = subprocess.run([ots, "--no-bitcoin", "--no-cache", "stamp", path], capture_output=True,
                               timeout=STAMP_TIMEOUT_S, env=env, stdin=subprocess.DEVNULL)
        except FileNotFoundError:
            raise StampError(f"cannot timestamp: {ots} is not installed (OpenTimestamps client; "
                             "FABRIC_SIGN_OTS names another)") from None
        except subprocess.TimeoutExpired:
            raise StampError(f"cannot timestamp: the calendars did not answer within {STAMP_TIMEOUT_S} s "
                             "(network?)") from None
        if p.returncode != 0:
            tail = p.stderr.decode(errors="replace").strip().splitlines()[-1:] or [f"exit {p.returncode}"]
            raise StampError(f"cannot timestamp: ots stamp failed ({tail[0]})")
        try:
            with open(path + ".ots", "rb") as f:
                proof = f.read()
        except OSError:
            raise StampError("cannot timestamp: ots stamp wrote no proof") from None
    if not matches(signature, proof):
        raise StampError("cannot timestamp: ots stamp wrote a proof of another file")
    return proof


class Spool:
    def __init__(self, directory: str):
        self.dir = directory

    @classmethod
    def of(cls, env: dict[str, str]) -> "Spool":
        explicit = env.get("FABRIC_SIGN_SPOOL")
        if explicit:
            return cls(explicit)
        state = env.get("XDG_STATE_HOME") or os.path.join(env.get("HOME") or os.path.expanduser("~"), ".local", "state")
        return cls(os.path.join(state, "agent-fabric", "ots-pending"))

    def _path(self, key: str) -> str:
        return os.path.join(self.dir, key + ".ots")

    def put(self, key: str, proof: bytes) -> None:
        os.makedirs(self.dir, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".put-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(proof)
            os.replace(tmp, self._path(key))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def get(self, key: str) -> bytes | None:
        try:
            with open(self._path(key), "rb") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def drop(self, key: str) -> None:
        try:
            os.unlink(self._path(key))
        except FileNotFoundError:
            pass

    def prune(self, now: float | None = None) -> None:
        cutoff = (time.time() if now is None else now) - SPOOL_MAX_AGE_S
        try:
            names = os.listdir(self.dir)
        except FileNotFoundError:
            return
        for name in names:
            path = os.path.join(self.dir, name)
            try:
                if name.endswith(".ots") and os.stat(path).st_mtime < cutoff:
                    os.unlink(path)
            except OSError:
                pass
