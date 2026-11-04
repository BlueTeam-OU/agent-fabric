"""tools/fabric/control/minisign.py — the check of a file against a minisign signature, with the standard library alone
(agent-fabric ADR-064 §5 rule 4, amendment 2026-10-31): fabric-python has hashlib.blake2b and no `cryptography`, and no
host is provisioned with the `minisign` program.

The signature is minisign's prehashed kind, the one a release job signs with: Ed25519 (RFC 8032 §5.1.7) over the
BLAKE2b-512 digest of the file, and a second Ed25519 signature, the global one, over the first signature's 64 bytes
followed by the trusted comment, so that the comment cannot be edited. The legacy kind ("Ed", Ed25519 over the file
itself) is refused: it is a different statement, and the pin names one kind.

The pin carries the three lines of the `.minisig` (the signature's base64, the trusted comment after "trusted comment: "
and the global signature's base64) and the public key's base64 line, so nothing about the signature is fetched.

Only a public key and public data are handled here, so nothing is constant-time and nothing is secret."""
from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Any

KEY_LEN = 42              # b"Ed" + key id (8) + Ed25519 public key (32)
SIG_LEN = 74              # b"ED" (prehashed) + key id (8) + Ed25519 signature (64)
GLOBAL_LEN = 64
CHUNK = 1 << 20


class SignatureError(Exception):
    """One line for a reply: which check failed."""


# --- Ed25519 verification, RFC 8032 section 5.1.7 ----------------------------------------------------------------
_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, -1, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _recover_x(y: int, sign: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, -1, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P:
        return None
    return _P - x if (x & 1) != sign else x


def _add(p: tuple[int, int, int, int], q: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    a = (p[1] - p[0]) * (q[1] - q[0]) % _P
    b = (p[1] + p[0]) * (q[1] + q[0]) % _P
    c = 2 * p[3] * q[3] * _D % _P
    d = 2 * p[2] * q[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return e * f % _P, g * h % _P, f * g % _P, e * h % _P


def _mul(s: int, p: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    q = (0, 1, 1, 0)
    while s:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _equal(p: tuple[int, int, int, int], q: tuple[int, int, int, int]) -> bool:
    return (p[0] * q[2] - q[0] * p[2]) % _P == 0 and (p[1] * q[2] - q[1] * p[2]) % _P == 0


def _decode(s: bytes) -> tuple[int, int, int, int] | None:
    n = int.from_bytes(s, "little")
    y = n & ((1 << 255) - 1)
    x = _recover_x(y, n >> 255)
    return None if x is None else (x, y, 1, x * y % _P)


_GY = 4 * pow(5, -1, _P) % _P
_GX = _recover_x(_GY, 0)
assert _GX is not None
_B = (_GX, _GY, 1, _GX * _GY % _P)


def ed25519_verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """RFC 8032 §5.1.7 with the cofactorless equation [S]B = R + [k]A; a malformed key, point or S >= L is False."""
    if len(public) != 32 or len(signature) != 64:
        return False
    a = _decode(public)
    r = _decode(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if a is None or r is None or s >= _L:
        return False
    k = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    return _equal(_mul(s, _B), _add(r, _mul(k, a)))


# --- minisign's encodings -----------------------------------------------------------------------------------------
def _b64(text: Any, length: int) -> bytes | None:
    if not isinstance(text, str):
        return None
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None
    # b64decode accepts non-zero padding bits; the canonical encoding is the only one the pin may hold.
    return raw if len(raw) == length and base64.b64encode(raw).decode() == text else None


def key_id_text(key_id: bytes) -> str:
    """The id as `minisign` prints it: the 8 bytes are little-endian."""
    return key_id[::-1].hex().upper()


def key_problem(public_key: Any, key_id: Any) -> str | None:
    """None for a public key line of 42 bytes, "Ed", whose id is key_id, else what is wrong."""
    raw = _b64(public_key, KEY_LEN)
    if raw is None or raw[:2] != b"Ed":
        return "has a public_key that is not minisign's 42 bytes starting Ed in base64"
    if key_id != key_id_text(raw[2:10]):
        return "has a key_id that is not the public key's"
    return None


def minisig_problem(minisig: Any, key_id: Any) -> str | None:
    """None for the three lines of a prehashed signature made by key_id, else what is wrong."""
    if not isinstance(minisig, dict) or set(minisig) != {"signature", "trusted_comment", "global_signature"}:
        return "has a minisig that is not signature, trusted_comment and global_signature"
    sig = _b64(minisig["signature"], SIG_LEN)
    if sig is None:
        return "has a signature that is not 74 bytes in base64"
    if sig[:2] == b"Ed":
        return "has a legacy signature (Ed), not the prehashed kind (ED)"
    if sig[:2] != b"ED":
        return "has a signature that does not start ED"
    if key_id_text(sig[2:10]) != key_id:
        return "has a signature made by another key than the release's"
    if _b64(minisig["global_signature"], GLOBAL_LEN) is None:
        return "has a global_signature that is not 64 bytes in base64"
    comment = minisig["trusted_comment"]
    if not isinstance(comment, str):
        return "has a trusted_comment that is not a string"
    try:
        comment.encode("utf-8")
    except UnicodeEncodeError:
        return "has a trusted_comment that is not valid UTF-8 text"
    return None


def verify_file(path: str, public_key: str, minisig: dict, name: str) -> None:
    """Raises SignatureError, naming the check that failed, unless the file at path is what minisig signs with public_key and the
    trusted comment names `file:<name>`. The pin's own shape is pin_problem's; a defect there is still refused here."""
    key = _b64(public_key, KEY_LEN)
    sig = _b64(minisig.get("signature"), SIG_LEN)
    glob = _b64(minisig.get("global_signature"), GLOBAL_LEN)
    comment = minisig.get("trusted_comment")
    if key is None or sig is None or glob is None or not isinstance(comment, str) or key[:2] != b"Ed" or sig[:2] != b"ED":
        raise SignatureError("the pinned key or signature is malformed, or is the legacy kind")
    if sig[2:10] != key[2:10]:
        raise SignatureError("the signature was made by another key than the pinned one")
    digest = hashlib.blake2b(digest_size=64)
    try:
        with open(path, "rb") as fh:
            while chunk := fh.read(CHUNK):
                digest.update(chunk)
    except OSError as e:
        raise SignatureError(f"the archive could not be read for its signature ({type(e).__name__})") from None
    if not ed25519_verify(key[10:], digest.digest(), sig[10:]):
        raise SignatureError("the archive's signature does not verify with the pinned key")
    if not ed25519_verify(key[10:], sig[10:] + comment.encode("utf-8"), glob):
        raise SignatureError("the trusted comment's signature does not verify with the pinned key")
    if f"file:{name}" not in comment.split("\t"):
        raise SignatureError(f"the signed trusted comment does not name file:{name}")
