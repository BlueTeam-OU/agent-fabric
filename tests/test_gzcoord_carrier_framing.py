#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/framing.py (ADR-064 rules 7, 8): a message
at or under the 48 KiB ceiling goes as it is; past it, compressed under
the carrier's media type; past it still, chunked and reassembled with a
digest check. Pure logic: no socket, no clock. Plain script: prints
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord.carrier import framing as f  # noqa: E402

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def raises(fn) -> bool:
    try:
        fn()
    except f.FramingError:
        return True
    return False


def roundtrip(payloads: list[f.Payload], source: str = "peer") -> str | None:
    r = f.Reassembler()
    out = None
    for p in payloads:
        if p.media_type == f.MEDIA_CHUNK:
            got = r.add(source, p.data)
            out = got[1] if got else out
        else:
            out = f.decode_message(p.media_type, p.data)
    return out


def noise(n: int) -> str:
    # incompressible but UTF-8: a hash chain in hex
    out, h, size = [], b"seed", 0
    while size < n:
        h = hashlib.sha256(h).digest()
        out.append(h.hex())
        size += 64
    return "".join(out)[:n]


def main() -> int:
    small = "x" * f.CEILING
    p = f.encode("m1", small)
    check("at the ceiling: one plain payload", len(p) == 1 and p[0].media_type == f.MEDIA_MESSAGE
          and f.encoding_of(p) == "plain" and roundtrip(p) == small)

    big = "line of text\n" * 20000          # 260 KB, compresses far under 48 KiB
    p = f.encode("m2", big)
    check("past the ceiling, compressible: one compressed payload",
          len(p) == 1 and p[0].media_type == f.MEDIA_MESSAGE + ";ce=deflate"
          and len(p[0].data) <= f.CEILING and f.encoding_of(p) == "compressed" and roundtrip(p) == big)

    hard = noise(f.CEILING * 2)             # hex noise: ~50% of its size
    p = f.encode("m3", hard)
    check("compressed still past the ceiling: chunked, every payload within it",
          len(p) >= 2 and f.encoding_of(p) == "chunked"
          and all(x.media_type == f.MEDIA_CHUNK and len(x.data) <= f.CEILING for x in p))
    check("chunks reassemble, in any order", roundtrip(p) == hard and roundtrip(list(reversed(p))) == hard)

    r = f.Reassembler()
    first = None
    for x in p + p[:1]:
        first = r.add("a", x.data) or first
    check("a repeated chunk after completion starts a new partial, delivers nothing",
          first is not None and r.add("a", p[0].data) is None)

    r = f.Reassembler()
    r.add("a", p[0].data)
    check("the same id from another source is another message",
          r.add("b", p[1].data) is None)

    tampered = bytearray(p[-1].data)
    tampered[-1] ^= 1
    r = f.Reassembler()
    for x in p[:-1]:
        r.add("a", x.data)
    check("a flipped byte fails the digest, nothing delivered",
          raises(lambda: r.add("a", bytes(tampered))))

    h, piece = f.parse_chunk(p[0].data)
    other = dict(h, sha256="0" * 64)
    r = f.Reassembler()
    r.add("a", p[0].data)
    check("chunks disagreeing on the whole are refused and the partial dropped",
          raises(lambda: r.add("a", json.dumps(other).encode() + b"\n" + piece)))

    for name, data in [
        ("no newline", b'{"id":"x"}'),
        ("header past its bound", b"{" + b" " * f.HEADER_MAX + b"}\n"),
        ("not JSON", b"nope\n"),
        ("extra key", json.dumps(dict(h, extra=1)).encode() + b"\n"),
        ("index out of range", json.dumps(dict(h, i=h["of"])).encode() + b"\n"),
        ("bool as index", json.dumps(dict(h, i=True)).encode() + b"\n"),
        ("count past the bound", json.dumps(dict(h, of=f.MAX_CHUNKS + 1)).encode() + b"\n"),
        ("a single-chunk 'chunked' message", json.dumps(dict(h, of=1)).encode() + b"\n"),
    ]:
        check(f"bad chunk header refused: {name}", raises(lambda d=data: f.parse_chunk(d)))

    check("unknown content-encoding refused", raises(lambda: f.decode_message(f.MEDIA_MESSAGE + ";ce=br", b"x")))
    check("unknown parameter refused", raises(lambda: f.decode_message(f.MEDIA_MESSAGE + ";x=1", b"x")))
    check("another media type refused", raises(lambda: f.decode_message("text/plain", b"x")))
    check("a message that is not UTF-8 refused", raises(lambda: f.decode_message(f.MEDIA_MESSAGE, b"\xff\xfe")))

    import zlib
    bomb = zlib.compress(b"\0" * (f.MAX_TEXT + 10))
    check("a decompression bomb is refused at the size bound",
          raises(lambda: f.decode_message(f.MEDIA_MESSAGE + ";ce=deflate", bomb)))
    check("a truncated stream is refused",
          raises(lambda: f.decode_message(f.MEDIA_MESSAGE + ";ce=deflate", zlib.compress(b"hello" * 99)[:-6])))

    check("a message past the size bound is refused at the sender",
          raises(lambda: f.encode("m", "x" * (f.MAX_TEXT + 1))))
    check("more chunks than the bound is refused at the sender",
          raises(lambda: f.encode("m", noise(f.MAX_TEXT))))

    print(f"\ntest_gzcoord_carrier_framing: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
