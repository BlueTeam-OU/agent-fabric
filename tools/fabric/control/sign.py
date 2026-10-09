"""tools/fabric/control/sign.py — the operator's signature on a control
request: runtime/control/sign.mjs in Python (ADR-040 Wave 8), unwired
until the cutover. The Node module stays the oracle until then.

CONTRACT, frozen from sign.mjs (the wire does not change, ADR-040 §5):
  ACTION_OPS, ACTION_TTL_MAX_S, KEY_PREFIX, PRIVATE_PREFIX   as Node's
  canonical(value)       the bytes Node's canonical() builds, as text:
                         JSON.stringify's, keys sorted at every depth
                         in UTF-16 code-unit order (Array.prototype.sort)
  sign_request(r, spec)  a copy of r with `sig`: Ed25519 over
                         canonical(every field but sig), base64
  verify_request(r, key) True only for a well-formed signature by
                         exactly this key over those bytes
  private_key_from(spec) / public_key_from(spec)
                         the DER key of `ed25519-pkcs8:<b64>` /
                         `ed25519:<b64>`, or None
  generate_operator_key()  {"privateKeySpec", "publicKeySpec"}

WHAT IS NOT NODE'S:
  - Python has no `undefined`: Node drops a key whose value is
    undefined, and such a key never reaches the wire, since
    JSON.stringify drops it there too. A Python request simply has no
    such key; None is null, signed as null, as Node signs null.
  - Node's crypto never fails to run; openssl can (missing, killed, a
    timeout, an answer it does not give). That is SignError, never
    False: "not signed by the operator" and "could not verify" are
    different answers, and a daemon that read the second as the first
    would refuse every action with a false reason.
  - A key is checked by openssl (`pkey -noout -text`), and only an
    Ed25519 one is a key: openssl's -rawin signs no other kind, and
    Node's sign(null, ...) over any other key is not what the fabric
    signs with.

WHY openssl, and how (docs/live-checks/2026-10-09-ed25519-through-
openssl.md, the points measured after it): the standard library has
no Ed25519. The private key reaches openssl through a pipe it reads as
/dev/fd/N, never a file and never argv. The message cannot: Ed25519
is one-shot and openssl refuses a pipe or stdin ("unable to determine
file size for oneshot operation", 3.0.13 and 3.5.8), so the signed
bytes — public — go in a 0600 file in a private directory, removed
after the call. One process per signature: 9 ms, 7 ms per verify.
"""
from __future__ import annotations

import base64
import decimal
import math
import os
import subprocess
import tempfile

ACTION_OPS = ["upgrade", "secrets-sync", "jobs-add", "local-prune", "secrets-selftest", "pool-add", "tools-install"]
ACTION_TTL_MAX_S = 600
KEY_PREFIX = "ed25519:"
PRIVATE_PREFIX = "ed25519-pkcs8:"   # one line: the store's entry is read as its first line (pass layout)

TIMEOUT_S = 10
VERIFIED = "Signature Verified Successfully"
MAX_BLOB = 4096           # a key or a signature, a few dozen bytes; a pipe holds 64 KiB
SIG_BYTES = 64            # every Ed25519 signature
NOT_VERIFIED = "Signature Verification Failure"


class SignError(Exception):
    """openssl could not answer: missing, timed out, or an answer that is
    neither a signature nor a verdict. Never a verdict itself."""


# ── canonical: JSON.stringify's bytes ───────────────────────────────────

_SHORT = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def js_string(s: str) -> str:
    """JSON.stringify(s) (well-formed, as Node has written it since 12):
    the short escapes, other controls as \\u00xx, a lone surrogate as
    \\udxxx, lower-case hex; everything else, U+2028 and DEL included,
    as itself. Read in UTF-16 code units, as JavaScript holds a string,
    so a surrogate pair held as two code points is one character."""
    units = s.encode("utf-16-be", "surrogatepass")
    out, i = ['"'], 0
    while i < len(units):
        u = int.from_bytes(units[i:i + 2], "big")
        i += 2
        if 0xD800 <= u <= 0xDBFF and i < len(units) and 0xDC00 <= int.from_bytes(units[i:i + 2], "big") <= 0xDFFF:
            low = int.from_bytes(units[i:i + 2], "big")
            i += 2
            out.append(chr(0x10000 + ((u - 0xD800) << 10) + (low - 0xDC00)))
        elif 0xD800 <= u <= 0xDFFF or u < 0x20:
            c = chr(u)
            out.append(_SHORT.get(c) or f"\\u{u:04x}")
        else:
            c = chr(u)
            out.append(_SHORT.get(c, c))
    out.append('"')
    return "".join(out)


def js_number(x: int | float) -> str:
    """JSON.stringify(x) of a JavaScript number (Number::toString): an
    integer is a double first, as JSON.parse makes it in Node; NaN and
    the infinities are null; -0 is 0; the shortest round-trip digits
    laid out by the spec's rules (plain up to 21 digits, an exponent
    from 1e21 and below 1e-6, `e+`/`e-`, no padding)."""
    try:
        f = float(x)
    except OverflowError:
        return "null"
    if math.isnan(f) or math.isinf(f):
        return "null"
    if f == 0:
        return "0"
    sign = "-" if f < 0 else ""
    t = decimal.Decimal(repr(abs(f))).as_tuple()
    digits = "".join(map(str, t.digits)).rstrip("0") or "0"
    n = len(t.digits) + t.exponent       # value = 0.<digits> × 10^n
    k = len(digits)
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * -n + digits
    else:
        e = n - 1
        body = (digits if k == 1 else digits[0] + "." + digits[1:]) + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return sign + body


def _utf16_key(k: str) -> bytes:
    # Big-endian UTF-16 bytes compare as the code units do: the order of
    # Array.prototype.sort(), where an astral character (a high surrogate,
    # 0xD800+) sorts before U+E000..U+FFFF, unlike Python's code points.
    return k.encode("utf-16-be", "surrogatepass")


def canonical(value) -> str:
    """sign.mjs canonical(): arrays in order, objects with their keys
    sorted at every depth, scalars as JSON.stringify writes them.

    Built with a stack of its own, not by recursion: a request off the
    relay may nest deeper than Python's recursion limit (about 500 here,
    two frames a level), which Node's canonical builds without trouble,
    and a RecursionError out of verify_request is no verdict (review of
    73f35649, F2). A container met again inside itself is a cycle — no
    JSON value has one — and a ValueError, never an endless build."""
    out: list[str] = []
    open_ids: set[int] = set()
    todo: list = [("value", value)]
    while todo:
        what, item = todo.pop()
        if what == "text":
            out.append(item)
            continue
        if what == "close":
            open_ids.discard(item)
            continue
        if isinstance(item, (list, dict)):
            if id(item) in open_ids:
                raise ValueError("canonical: a value that contains itself")
            open_ids.add(id(item))
            todo.append(("close", id(item)))
            if isinstance(item, list):
                todo.append(("text", "]"))
                for i in range(len(item) - 1, -1, -1):
                    todo.append(("value", item[i]))
                    if i:
                        todo.append(("text", ","))
                todo.append(("text", "["))
            else:
                if not all(isinstance(k, str) for k in item):
                    raise TypeError("canonical: an object's keys are strings")
                keys = sorted(item, key=_utf16_key)
                todo.append(("text", "}"))
                for i in range(len(keys) - 1, -1, -1):
                    todo.append(("value", item[keys[i]]))
                    todo.append(("text", js_string(keys[i]) + ":"))
                    if i:
                        todo.append(("text", ","))
                todo.append(("text", "{"))
            continue
        out.append(_scalar(item))
    return "".join(out)


def _scalar(value) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return js_string(value)
    if isinstance(value, (int, float)):
        return js_number(value)
    raise TypeError(f"canonical: {type(value).__name__} is not a JSON value")


def payload(request: dict) -> bytes:
    """What the signature covers: every field but `sig`."""
    rest = {k: v for k, v in request.items() if k != "sig"}
    # A lone surrogate is escaped by js_string, so the text always encodes.
    return canonical(rest).encode("utf-8")


_B64 = {c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")}
_B64.update({"-": 62, "_": 63})


def node_b64decode(text: str) -> bytes:
    """Buffer.from(text, 'base64'), byte for byte: both alphabets (the
    URL-safe - and _ too), anything else skipped, the end at the first
    `=`, and a last lone sextet dropped. Python's b64decode differs on
    each (it refuses or reads past them), so a key or a signature Node
    reads one way would be read another here."""
    # Node reads a string for base64 by the low byte of each UTF-16 code
    # unit: U+0141 is "A", and the high surrogate U+D83D (of U+1F600) is
    # "=", which ends it (review of 73f35649, F3, measured on Node 22.22.2).
    units = text.encode("utf-16-le", "surrogatepass")
    bits, nbits, out = 0, 0, bytearray()
    for c in map(chr, units[0::2]):
        if c == "=":
            break
        v = _B64.get(c)
        if v is None:
            continue
        bits, nbits = (bits << 6) | v, nbits + 6
        if nbits >= 8:
            nbits -= 8
            out.append((bits >> nbits) & 0xFF)
    return bytes(out)


# ── openssl ─────────────────────────────────────────────────────────────

def _run(args: list[str], *, data: bytes | None = None, fds: dict[int, bytes] | None = None,
         message: bytes | None = None) -> subprocess.CompletedProcess:
    """`openssl <args>`. Each `fds` entry is written to a pipe the child
    reads as /dev/fd/<that pipe>, its placeholder `{fd<n>}` in args
    replaced; `message` goes in a 0600 file named by `{message}`."""
    pipes, opened = {}, []
    for blob in (fds or {}).values():
        # Written before the child exists, so a blob that fills a pipe
        # (64 KiB) would block for good, the timeout never reached: the
        # callers bound what they pass far below it (review of 73f35649, F1).
        if len(blob) > MAX_BLOB:
            raise ValueError(f"a {len(blob)}-byte blob for openssl: at most {MAX_BLOB}")
    try:
        for name, blob in (fds or {}).items():
            r, w = os.pipe()
            opened += [r, w]
            os.write(w, blob)
            os.close(w)
            opened.remove(w)
            pipes[name] = r
        with tempfile.TemporaryDirectory(prefix="fabric-sign-") as d:
            argv = [a.format(**{f"fd{n}": f"/dev/fd/{fd}" for n, fd in pipes.items()},
                             message=os.path.join(d, "message")) for a in args]
            if message is not None:
                fd = os.open(os.path.join(d, "message"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    os.write(fd, message)
                finally:
                    os.close(fd)
            try:
                return subprocess.run(["openssl", *argv], input=data, capture_output=True, timeout=TIMEOUT_S,
                                      pass_fds=tuple(pipes.values()), **({} if data is not None else {"stdin": subprocess.DEVNULL}))
            except FileNotFoundError:
                raise SignError("openssl is not installed") from None
            except subprocess.TimeoutExpired:
                raise SignError(f"openssl {args[0]}: no answer within {TIMEOUT_S} s") from None
    finally:
        for fd in opened:
            os.close(fd)


def _key_from(spec, prefix: str, public: bool) -> bytes | None:
    if not isinstance(spec, str) or not spec.startswith(prefix):
        return None
    der = node_b64decode(spec[len(prefix):])
    if len(der) > MAX_BLOB:
        return None
    # -passin pass: (empty, no secret): an encrypted key is refused, never
    # a passphrase prompt on the terminal that waits out the timeout.
    r = _run(["pkey", *(["-pubin"] if public else []), "-inform", "DER", "-in", "{fd0}", "-passin", "pass:",
              "-noout", "-text"], fds={0: der})
    want = "ED25519 Public-Key:" if public else "ED25519 Private-Key:"
    if r.returncode != 0 or not r.stdout.decode("utf-8", "replace").startswith(want):
        return None
    return der


def private_key_from(spec) -> bytes | None:
    return _key_from(spec, PRIVATE_PREFIX, public=False)


def public_key_from(spec) -> bytes | None:
    return _key_from(spec, KEY_PREFIX, public=True)


def sign_request(request: dict, private_spec) -> dict:
    key = private_key_from(private_spec)
    if key is None:
        raise ValueError("not an operator signing key (ed25519-pkcs8:<base64>)")
    r = _run(["pkeyutl", "-sign", "-rawin", "-keyform", "DER", "-inkey", "{fd0}", "-passin", "pass:", "-in", "{message}"],
             fds={0: key}, message=payload(request))
    if r.returncode != 0 or len(r.stdout) != 64:
        raise SignError(f"openssl pkeyutl -sign: exit {r.returncode}, {len(r.stdout)} bytes: "
                        f"{r.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return {**request, "sig": base64.b64encode(r.stdout).decode("ascii")}


def verify_request(request, public_key: bytes | None) -> bool:
    """True only for a well-formed signature by exactly this key; False
    for any other signature or none; SignError when openssl could not
    say which."""
    if not public_key or not isinstance(request, dict):
        return False
    sig = request.get("sig")
    if not isinstance(sig, str) or not sig:
        return False
    raw = node_b64decode(sig)
    if len(raw) != SIG_BYTES:
        # Node's verify says false to any other length; asking openssl
        # would also write an unbounded relay value into a pipe.
        return False
    try:
        message = payload(request)
    except (TypeError, ValueError):
        # Node's canonical throws on what it cannot build, and its verify
        # catches that as false.
        return False
    r = _run(["pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER", "-inkey", "{fd0}", "-in", "{message}",
              "-sigfile", "{fd1}"], fds={0: public_key, 1: raw}, message=message)
    said = r.stdout.decode("utf-8", "replace").strip()
    if r.returncode == 0 and said == VERIFIED:
        return True
    if r.returncode == 1 and said == NOT_VERIFIED:
        return False
    raise SignError(f"openssl pkeyutl -verify: exit {r.returncode}, {said!r}: "
                    f"{r.stderr.decode('utf-8', 'replace').strip()[:200]}")


def generate_operator_key() -> dict:
    """A new operator key pair: the private half for the operator's own
    store, the public half for runtime/hosts/registry.json. The private
    key passes between the two openssl calls through pipes only."""
    gen = _run(["genpkey", "-algorithm", "ed25519", "-outform", "DER"])
    if gen.returncode != 0 or not gen.stdout:
        raise SignError(f"openssl genpkey: exit {gen.returncode}")
    pub = _run(["pkey", "-inform", "DER", "-in", "{fd0}", "-pubout", "-outform", "DER"], fds={0: gen.stdout})
    if pub.returncode != 0 or not pub.stdout:
        raise SignError(f"openssl pkey -pubout: exit {pub.returncode}")
    return {"privateKeySpec": PRIVATE_PREFIX + base64.b64encode(gen.stdout).decode("ascii"),
            "publicKeySpec": KEY_PREFIX + base64.b64encode(pub.stdout).decode("ascii")}
